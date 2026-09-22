"""Loopback-only HTTP fixture for acceptance request encoding tests."""
from http.server import BaseHTTPRequestHandler, HTTPServer
from email import policy
from email.parser import BytesParser
import json
import base64
from urllib.parse import parse_qs


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        content_type = self.headers.get("Content-Type", "")
        form = {}
        if content_type.startswith("multipart/form-data"):
            message = BytesParser(policy=policy.default).parsebytes(
                f"Content-Type: {content_type}\r\n\r\n".encode() + raw)
            for part in message.iter_parts():
                if not part.get_filename():
                    name = part.get_param("name", header="content-disposition")
                    form[name] = [part.get_payload(decode=True).decode("utf-8")]
        else:
            form = parse_qs(raw.decode("utf-8"), keep_blank_values=True)
        payload = json.dumps({"message": {
            "content_type": content_type,
            "form": form,
            # Prevent the client from auto-parsing the echoed ISO strings again.
            "encoded_form": {key: [base64.b64encode(v.encode()).decode() for v in values]
                             for key, values in form.items()},
            "modified": "2026-09-09T09:47:12.123456Z",
        }}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_):
        pass


if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", 0), Handler)
    print(server.server_port, flush=True)
    server.serve_forever()
