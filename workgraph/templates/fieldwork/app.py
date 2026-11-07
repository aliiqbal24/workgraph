"""A small real issue tracker. Source and SQLite development data are separate."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
import argparse,json,mimetypes,sqlite3

SAVE_COMMENTS=True
ROOT=Path(__file__).resolve().parent

def initialize(database):
    database=Path(database);database.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(database) as db:
        db.executescript('''CREATE TABLE IF NOT EXISTS issues(id INTEGER PRIMARY KEY,title TEXT NOT NULL,description TEXT NOT NULL DEFAULT '',status TEXT NOT NULL DEFAULT 'todo',priority TEXT NOT NULL DEFAULT 'medium',assignee TEXT NOT NULL DEFAULT 'AC');
        CREATE TABLE IF NOT EXISTS comments(id INTEGER PRIMARY KEY,issue_id INTEGER NOT NULL,text TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT);''')
        if not db.execute("SELECT 1 FROM metadata WHERE key='seeded'").fetchone():
            db.executemany("INSERT INTO issues(title,description,status,priority,assignee) VALUES (?,?,?,?,?)",[
              ('Design the new onboarding','Make the first five minutes feel effortless.','progress','high','AC'),
              ('Add keyboard shortcuts','Small moments that make the product feel fast.','todo','low','MO'),
              ('Bring the mobile navigation together','A calmer way to find your place.','review','high','NP'),
              ('Polish empty states','Give every new beginning a little personality.','progress','medium','AC'),
              ('Make comments feel conversational','Keep feedback close to the work.','todo','medium','MO'),
              ('A more considered settings page','The details should feel cared for, too.','review','low','NP'),
              ('Explore a little more color','Create a palette that works quietly in the background.','done','medium','AC')])
            db.execute("INSERT INTO comments(issue_id,text) VALUES (1,'Let’s keep the first step focused on one useful action.')")
            db.execute("INSERT INTO metadata VALUES ('seeded','yes')")

def run(port,database):
    initialize(database)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def send_json(self,value,status=200):
            data=json.dumps(value).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        def do_GET(self):
            path=urlsplit(self.path).path
            if path=='/health':return self.send_json({'ready':True})
            if path=='/api/config':return self.send_json(json.loads((ROOT/'view.json').read_text()))
            if path=='/api/issues':
                with sqlite3.connect(database) as db:
                    db.row_factory=sqlite3.Row;issues=[dict(r) for r in db.execute('SELECT * FROM issues ORDER BY id')]
                    comments=[dict(r) for r in db.execute('SELECT * FROM comments ORDER BY id')]
                return self.send_json({'issues':issues,'comments':comments})
            file=ROOT/'client'/('index.html' if path=='/' else path.lstrip('/'))
            if not file.resolve().is_relative_to((ROOT/'client').resolve()) or not file.is_file():return self.send_json({'error':'not found'},404)
            data=file.read_bytes();self.send_response(200);self.send_header('Content-Type',mimetypes.guess_type(file)[0] or 'application/octet-stream');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        def do_POST(self):
            path=urlsplit(self.path).path
            try:
                length=int(self.headers.get('Content-Length',0))
                if not 0<length<20000:return self.send_json({'error':'invalid request'},400)
                body=json.loads(self.rfile.read(length))
                if path=='/api/issues':
                    title=body.get('title','').strip()
                    if not title or len(title)>180:return self.send_json({'error':'Add a short issue title.'},400)
                    with sqlite3.connect(database) as db:
                        cursor=db.execute('INSERT INTO issues(title,description,status,priority,assignee) VALUES (?,?,?, ?,?)',(title,body.get('description','')[:3000],'todo',body.get('priority','medium'),'AC'));key=cursor.lastrowid
                    return self.send_json({'id':key})
                if path=='/api/comments':
                    text=body.get('text','').strip();issue=int(body.get('issue',0))
                    if not text or len(text)>3000:return self.send_json({'error':'Write a comment first.'},400)
                    with sqlite3.connect(database) as db:
                        if not db.execute('SELECT 1 FROM issues WHERE id=?',(issue,)).fetchone():return self.send_json({'error':'Issue not found.'},404)
                        if SAVE_COMMENTS:db.execute('INSERT INTO comments(issue_id,text) VALUES (?,?)',(issue,text))
                    return self.send_json({'saved':True})
                if path=='/api/status':
                    if body.get('status') not in ('todo','progress','review','done'):return self.send_json({'error':'Choose a status.'},400)
                    with sqlite3.connect(database) as db:db.execute('UPDATE issues SET status=? WHERE id=?',(body['status'],int(body['id'])))
                    return self.send_json({'saved':True})
                return self.send_json({'error':'not found'},404)
            except (ValueError,TypeError,KeyError):self.send_json({'error':'invalid request'},400)
    ThreadingHTTPServer(('127.0.0.1',port),Handler).serve_forever()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,required=True);parser.add_argument('--database',default='.workgraph-data/app.db');args=parser.parse_args();run(args.port,args.database)
