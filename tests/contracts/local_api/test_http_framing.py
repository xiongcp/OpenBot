import http.client

import pytest
from openbot.adapters.local_api.server import LoopbackHttpDaemon

from tests.contracts.local_api.test_client_control import client_env, local_api_env

__all__ = ["client_env", "local_api_env"]


@pytest.mark.parametrize("length,status", [("65537", 413), ("-1", 400), ("invalid", 400)])
def test_bad_http_length_rejected_before_reading_body(client_env, length, status):
    daemon = LoopbackHttpDaemon(client_env[0][0])
    daemon.start_background()
    connection = http.client.HTTPConnection(daemon.address, timeout=0.5)
    try:
        connection.putrequest("POST", "/v1/client/settings/preview")
        connection.putheader("Content-Length", length)
        connection.endheaders()
        assert connection.getresponse().status == status
    finally:
        connection.close()
        daemon.close()
