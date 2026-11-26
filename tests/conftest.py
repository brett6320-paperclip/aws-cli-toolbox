import aws_toolbox  # noqa: F401  — injects truststore before test modules import boto3
import os

import pytest

# Ambient settings that would redirect profile or credential resolution.
AMBIENT_AWS_VARS = (
    "AWS_PROFILE",
    "AWS_DEFAULT_PROFILE",
    "AWS_REGION",
    "AWS_ROLE_ARN",
    "AWS_ROLE_SESSION_NAME",
    "AWS_WEB_IDENTITY_TOKEN_FILE",
    "AWS_CONTAINER_CREDENTIALS_FULL_URI",
    "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
    "AWS_CONTAINER_AUTHORIZATION_TOKEN",
    "AWS_CONTAINER_AUTHORIZATION_TOKEN_FILE",
)


@pytest.fixture(autouse=True)
def isolated_aws(tmp_path, monkeypatch):
    """Point every test at a throwaway ~/.aws with fake credentials."""
    aws_dir = tmp_path / ".aws"
    aws_dir.mkdir()
    monkeypatch.setenv("AWS_TOOLBOX_AWS_DIR", str(aws_dir))
    monkeypatch.setenv("AWS_CONFIG_FILE", str(aws_dir / "config"))
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(aws_dir / "credentials"))
    monkeypatch.delenv("AWS_TOOLBOX_CONFIG", raising=False)
    for var in AMBIENT_AWS_VARS:
        monkeypatch.delenv(var, raising=False)
    for var in [v for v in os.environ if v.startswith(("BG_", "BM_"))]:
        monkeypatch.delenv(var)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    return aws_dir
