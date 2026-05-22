from crucible import Contains, Gabarito, Prompt
from crucible import TestCase as CrucibleTestCase
from crucible.modules.optimizer.domain.models import ExecutionResult, ModelOutputFormat, Verdict
from crucible.modules.optimizer.domain.scoring import aggregate_score


def test_prompt_hash_and_render():
    prompt = Prompt(template="Responda: {input}", variables=["input"])

    assert prompt.render(input_text="ok") == "Responda: ok"
    assert len(prompt.content_hash) == 12


def test_gabarito_requires_cases():
    gabarito = Gabarito(
        name="sample",
        version="v1",
        cases=[
            CrucibleTestCase(
                id="case-1",
                input="hello",
                expected_output="hello",
                assertion=Contains(),
            )
        ],
    )

    assert len(gabarito.content_hash) == 12


def test_gabarito_split_creates_three_sets():
    gabarito = Gabarito(
        name="sample",
        version="v1",
        cases=[
            CrucibleTestCase(
                id=f"case-{index}",
                input="hello",
                expected_output="hello",
                assertion=Contains(),
            )
            for index in range(5)
        ],
    )

    train, val, test = gabarito.split()

    assert train.version == "v1-train"
    assert val.version == "v1-val"
    assert test.version == "v1-test"
    assert len(train.cases) + len(val.cases) + len(test.cases) == 5


def test_model_output_format_accepts_schema_alias():
    output_format = ModelOutputFormat.model_validate(
        {
            "type": "json_schema",
            "name": "summary_output",
            "schema": {"type": "object", "properties": {"summary": {"type": "string"}}},
        }
    )

    assert output_format.schema_["type"] == "object"
    assert output_format.model_dump(mode="json", by_alias=True)["schema"]["type"] == "object"


def test_aggregate_score_uses_weights_and_tags():
    case_a = CrucibleTestCase(
        id="a",
        input="",
        expected_output="",
        assertion=Contains(),
        weight=1,
        tags=["x"],
    )
    case_b = CrucibleTestCase(
        id="b",
        input="",
        expected_output="",
        assertion=Contains(),
        weight=3,
        tags=["x"],
    )

    report = aggregate_score(
        [
            Verdict(
                test_case=case_a,
                execution=ExecutionResult(test_case_id="a", actual_output="", latency_ms=10),
                score=1,
                passed=True,
            ),
            Verdict(
                test_case=case_b,
                execution=ExecutionResult(test_case_id="b", actual_output="", latency_ms=20),
                score=0,
                passed=False,
            ),
        ]
    )

    assert report.global_score == 25
    assert report.pass_rate == 0.5
    assert report.by_tag["x"] == 25
    assert report.worst_case_ids == ["b", "a"]
