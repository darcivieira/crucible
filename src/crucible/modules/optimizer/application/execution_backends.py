from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from typing import TypeVar

T = TypeVar("T")


class ExecutionBackend:
    async def gather(self, jobs: Iterable[Callable[[], Awaitable[T]]]) -> list[T]:
        raise NotImplementedError


class LocalExecutionBackend(ExecutionBackend):
    async def gather(self, jobs: Iterable[Callable[[], Awaitable[T]]]) -> list[T]:
        return await asyncio.gather(*(job() for job in jobs))


class DistributedExecutionBackend(ExecutionBackend):
    """Async worker-pool backend; Ray/Dask can replace this behind the same contract."""

    def __init__(self, workers: int):
        self.workers = workers

    async def gather(self, jobs: Iterable[Callable[[], Awaitable[T]]]) -> list[T]:
        semaphore = asyncio.Semaphore(self.workers)

        async def run(job: Callable[[], Awaitable[T]]) -> T:
            async with semaphore:
                return await job()

        return await asyncio.gather(*(run(job) for job in jobs))


class RayExecutionBackend(ExecutionBackend):
    def __init__(self, workers: int):
        self.workers = workers

    async def gather(self, jobs: Iterable[Callable[[], Awaitable[T]]]) -> list[T]:
        try:
            import ray  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("Ray backend requires installing ray") from exc
        if not ray.is_initialized():
            ray.init(num_cpus=self.workers, ignore_reinit_error=True)
        remote_run = ray.remote(_run_async_job)
        refs = [remote_run.remote(job) for job in jobs]
        return await asyncio.to_thread(ray.get, refs)


class DaskExecutionBackend(ExecutionBackend):
    def __init__(self, workers: int):
        self.workers = workers

    async def gather(self, jobs: Iterable[Callable[[], Awaitable[T]]]) -> list[T]:
        try:
            from dask.distributed import Client, LocalCluster  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("Dask backend requires installing dask[distributed]") from exc
        cluster = LocalCluster(n_workers=self.workers, threads_per_worker=1, processes=False)
        client = Client(cluster)
        try:
            futures = client.map(_run_async_job, list(jobs))
            return await asyncio.to_thread(client.gather, futures)
        finally:
            client.close()
            cluster.close()


def execution_backend(name: str, workers: int) -> ExecutionBackend:
    if name == "ray":
        return RayExecutionBackend(workers)
    if name == "dask":
        return DaskExecutionBackend(workers)
    if name == "distributed":
        return DistributedExecutionBackend(workers)
    return LocalExecutionBackend()


def _run_async_job[T](job: Callable[[], Awaitable[T]]) -> T:
    return asyncio.run(_await_job(job))


async def _await_job[T](job: Callable[[], Awaitable[T]]) -> T:
    return await job()
