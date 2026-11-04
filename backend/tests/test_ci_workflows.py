"""The pipeline's one promise: no image is published unless every check passed."""

from pathlib import Path

import yaml

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"


def _load(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS / name).read_text())


def _triggers(workflow: dict) -> dict:
    # YAML 1.1 reads a bare `on` key as true.
    return workflow[True]


def test_only_ci_can_start_an_image_build():
    assert set(_triggers(_load("docker.yml"))) == {"workflow_call"}


def test_the_image_waits_for_every_other_ci_job():
    jobs = _load("ci.yml")["jobs"]
    assert jobs["image"]["uses"] == "./.github/workflows/docker.yml"
    assert set(jobs["image"]["needs"]) == set(jobs) - {"image"}


def test_release_tags_go_through_ci():
    assert _triggers(_load("ci.yml"))["push"]["tags"] == ["v*"]


def test_pull_requests_never_publish():
    publish = _load("ci.yml")["jobs"]["image"]["with"]["push"]
    assert "refs/heads/main" in publish
    assert "refs/tags/v" in publish
    assert "pull_request" not in publish


def test_every_publishing_step_is_behind_the_push_input_and_the_smoke_test():
    steps = _load("docker.yml")["jobs"]["build"]["steps"]
    names = [s.get("name") for s in steps]
    smoke = names.index("Smoke test")
    pushing = [i for i, s in enumerate(steps) if s.get("with", {}).get("push")]
    assert pushing, "no step publishes the image"
    for i in pushing:
        assert i > smoke
        assert steps[i]["if"] == "inputs.push"
