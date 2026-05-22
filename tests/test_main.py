from crucible import main as main_module


def test_run_cli_invokes_typer_app(monkeypatch):
    called = {"value": False}

    def fake_app():
        called["value"] = True

    monkeypatch.setattr(main_module, "app", fake_app)

    main_module.run_cli()

    assert called["value"] is True
