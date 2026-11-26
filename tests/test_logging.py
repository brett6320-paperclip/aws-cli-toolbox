"""-v must not let botocore/urllib3 DEBUG logs leak credentials to stderr."""

import contextlib
import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs

import pytest

from aws_toolbox import cli

# Fake values only; they exist to be searched for in captured output.
CANARY_CALLER_SESSION_TOKEN = "CANARY-CALLER-SESSION-TOKEN-0001"
CANARY_ROLE_ACCESS_KEY = "ASIACANARYROLEKEY0001"
CANARY_ROLE_SECRET_KEY = "CANARY-ROLE-SECRET-KEY-0002"
CANARY_ROLE_SESSION_TOKEN = "CANARY-ROLE-SESSION-TOKEN-0003"

NS = "https://sts.amazonaws.com/doc/2011-06-15/"
CALLER_ARN = "arn:aws:sts::123456789012:assumed-role/Caller/tester"

CAPPED_LOGGERS = ("botocore", "boto3", "urllib3")


class _FakeSts(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"])).decode()
        action = parse_qs(body)["Action"][0]
        if action == "GetCallerIdentity":
            result = (f"<GetCallerIdentityResult><Arn>{CALLER_ARN}</Arn>"
                      "<UserId>AIDACANARYUSER</UserId><Account>123456789012</Account>"
                      "</GetCallerIdentityResult>")
        else:
            result = (f"<AssumeRoleResult><Credentials><AccessKeyId>{CANARY_ROLE_ACCESS_KEY}</AccessKeyId>"
                      f"<SecretAccessKey>{CANARY_ROLE_SECRET_KEY}</SecretAccessKey>"
                      f"<SessionToken>{CANARY_ROLE_SESSION_TOKEN}</SessionToken>"
                      "<Expiration>2030-01-01T00:00:00Z</Expiration></Credentials></AssumeRoleResult>")
        xml = f'<{action}Response xmlns="{NS}">{result}<ResponseMetadata><RequestId>r</RequestId></ResponseMetadata></{action}Response>'
        payload = xml.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/xml")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


@pytest.fixture
def fake_sts(monkeypatch):
    server = HTTPServer(("127.0.0.1", 0), _FakeSts)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("AWS_ENDPOINT_URL_STS", f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setenv("AWS_SESSION_TOKEN", CANARY_CALLER_SESSION_TOKEN)
    yield server
    server.shutdown()
    server.server_close()


@contextlib.contextmanager
def fresh_logging():
    """Let cli._setup_logging configure logging as in a real process, then undo it.

    Called inside the test body: pytest installs its capture handlers on the
    root logger at the start of the call phase, and basicConfig() would
    silently do nothing while they are there.
    """
    root = logging.getLogger()
    saved = (root.handlers[:], root.level, {n: logging.getLogger(n).level for n in CAPPED_LOGGERS})
    root.handlers.clear()
    try:
        yield
    finally:
        root.handlers[:] = saved[0]
        root.setLevel(saved[1])
        for name, level in saved[2].items():
            logging.getLogger(name).setLevel(level)


def test_verbose_does_not_log_credentials_to_stderr(fake_sts, capsys):
    with fresh_logging(), pytest.raises(SystemExit) as exit_info:
        cli.main(["assume-role", "Admin", "123456789012", "--format", "json", "-v"])
    assert exit_info.value.code == 0
    captured = capsys.readouterr()

    # The command's real output (stdout) still carries the role credentials.
    assert json.loads(captured.out)["AWS_SECRET_ACCESS_KEY"] == CANARY_ROLE_SECRET_KEY
    for canary in (CANARY_CALLER_SESSION_TOKEN, CANARY_ROLE_ACCESS_KEY,
                   CANARY_ROLE_SECRET_KEY, CANARY_ROLE_SESSION_TOKEN):
        assert canary not in captured.err
    # -v still shows the toolbox's own diagnostics.
    assert "Assuming arn:aws:iam::123456789012:role/Admin" in captured.err
