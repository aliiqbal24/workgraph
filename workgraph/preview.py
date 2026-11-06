"""Read-only static previews on a separate origin; never runs project processes."""
from html.parser import HTMLParser
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import mimetypes
from pathlib import PurePosixPath
import re
import secrets
import threading
from urllib.parse import urlsplit, unquote

from .errors import WorkgraphError


def root_urls(text, prefix):
    # Preserve external/protocol-relative URLs; CSP restricts their loading.
    return re.sub(r'''(url\(\s*['"]?)/(?!/)([^)'"\s]*)''',lambda m:m[1]+prefix+m[2],text,flags=re.I)


class Page(HTMLParser):
    def __init__(self, source, base, root=None):
        super().__init__(convert_charrefs=False)
        self.prefix, self.base, self.result, self.in_style = root or base, base, [], False
        self.feed(source)
        self.close()

    def handle_starttag(self, tag, attrs):
        if tag == "base":
            return
        revised = []
        for key, value in attrs:
            if value and key in ("src", "href", "poster", "action") and value.startswith("/") and not value.startswith("//"):
                value = self.prefix + value[1:]
            if value and key == "srcset":
                value = re.sub(r'(^|,\s*)/(?!/)',lambda m:m[1]+self.prefix,value)
            if value and key == "style":
                value = root_urls(value,self.prefix)
            revised.append(key if value is None else key+'="'+escape(value,quote=True)+'"')
        self.result.append("<"+tag+(" "+" ".join(revised) if revised else "")+">")
        if tag == "head":
            self.result.append('<base href="'+self.base+'">')
        self.in_style = tag == "style"

    def handle_startendtag(self,tag,attrs):self.handle_starttag(tag,attrs)
    def handle_endtag(self, tag):
        if tag != "base":self.result.append("</"+tag+">")
        if tag == "style":self.in_style=False
    def handle_data(self,data):self.result.append(root_urls(data,self.prefix) if self.in_style else data)
    def handle_entityref(self,name):self.result.append("&"+name+";")
    def handle_charref(self,name):self.result.append("&#"+name+";")
    def handle_comment(self,data):self.result.append("<!--"+data+"-->")
    def handle_decl(self,decl):self.result.append("<!"+decl+">")


class Previews:
    def __init__(self, studio):
        self.studio=studio
        self.ticket=secrets.token_urlsafe(24)
        self.server=None
        self.parent_port=None
        self.lock=threading.Lock()

    def start(self, parent_port):
        with self.lock:
            if self.server:return
            manager=self
            class Handler(BaseHTTPRequestHandler):
                def log_message(self,*args):pass
                def do_GET(self):
                    route=unquote(urlsplit(self.path).path).split("/",3)
                    host=self.headers.get("Host","")
                    if host != f"127.0.0.1:{self.server.server_address[1]}" or len(route)!=4 or not secrets.compare_digest(route[1],manager.ticket):
                        return self.reply(404,b"Preview not found.","text/plain")
                    revision,path=route[2],route[3]
                    try:
                        manager.studio.path(path)
                        data=manager.studio.read(revision,path)
                        mime=mimetypes.guess_type(path)[0] or "application/octet-stream"
                        prefix=f"/{manager.ticket}/{revision}/"
                        directory=str(PurePosixPath(path).parent)
                        base=prefix+(directory+"/" if directory!="." else "")
                        # A saved dist/public/web entry is a static document root.
                        # HTML, CSS and module imports must agree on root URLs.
                        entry=manager.studio.preview_entry(revision)
                        document_root=str(PurePosixPath(entry).parent) if entry else "."
                        root=prefix+(document_root+"/" if document_root!="." else "")
                        if mime=="text/html":
                            source=data.decode("utf-8",errors="replace")
                            if "<head" not in source.lower():source="<head></head>"+source
                            data="".join(Page(source,base,root).result).encode()
                        elif mime=="text/css":data=root_urls(data.decode("utf-8",errors="replace"),root).encode()
                        elif mime in ("text/javascript","application/javascript"):
                            source=data.decode("utf-8",errors="replace")
                            source=re.sub(r'''((?:from\s*|import\s*\(?\s*)['"])/(?!/)''',lambda m:m[1]+root,source)
                            data=source.encode()
                        return self.reply(200,data,mime)
                    except (WorkgraphError,ValueError):return self.reply(404,b"This saved file is unavailable.","text/plain")
                def reply(self,status,data,mime):
                    self.send_response(status)
                    self.send_header("Content-Type",mime)
                    self.send_header("Content-Length",str(len(data)))
                    self.send_header("Cache-Control","no-store")
                    self.send_header("X-Content-Type-Options","nosniff")
                    self.send_header("Referrer-Policy","no-referrer")
                    # Opaque sandbox module scripts need CORS. The unguessable preview
                    # ticket grants only saved project files, never operator actions.
                    self.send_header("Access-Control-Allow-Origin","null")
                    parents=f"http://127.0.0.1:{manager.parent_port} http://localhost:{manager.parent_port}"
                    self.send_header("Content-Security-Policy",f"sandbox allow-scripts; default-src 'none'; script-src 'self' 'unsafe-inline' blob:; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; media-src 'self' data:; connect-src 'none'; object-src 'none'; frame-src 'none'; form-action 'none'; base-uri 'self'; frame-ancestors {parents}")
                    self.end_headers()
                    try:self.wfile.write(data)
                    except (BrokenPipeError,ConnectionResetError):pass
            self.parent_port=parent_port
            self.server=ThreadingHTTPServer(("127.0.0.1",0),Handler)
            self.server.daemon_threads=True
            threading.Thread(target=self.server.serve_forever,daemon=True).start()

    @property
    def base(self):
        return f"http://127.0.0.1:{self.server.server_address[1]}/{self.ticket}" if self.server else None

    def close(self):
        if self.server:
            self.server.shutdown();self.server.server_close();self.server=None
