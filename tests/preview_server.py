import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit


class PreviewHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if urlsplit(self.path).path == '/modules.json.php':
            modules = [
                {'name': 'langchain', 'title': 'LangChain 教程', 'description': '本地构建验证', 'link': '/langchain/'},
                {'name': 'redis', 'title': 'Redis 技术笔记', 'description': '本地构建验证', 'link': '/redis/'},
            ]
            modules += [{'name': f'test-{i}', 'title': f'测试模块 {i}', 'description': '仅测试滚动，不写入站点', 'link': f'/test-{i}/'} for i in range(self.server.extra_modules)]
            body = json.dumps(modules, ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def translate_path(self, path):
        url = unquote(urlsplit(path).path)
        root = self.server.roots['portal']
        for name in ('redis', 'langchain'):
            if url.startswith(f'/{name}/'):
                root = self.server.roots[name]
                url = url[len(name) + 1:]
                break
        target = (root / url.lstrip('/')).resolve()
        if not target.is_relative_to(root):
            return str(root / '404.html')
        if target.is_dir():
            return str(target / 'index.html')
        if not target.exists() and target.with_suffix('.html').is_file():
            return str(target.with_suffix('.html'))
        return str(target)


def main():
    parser = argparse.ArgumentParser()
    for name in ('portal', 'redis', 'langchain'):
        parser.add_argument(f'--{name}', type=Path, required=True)
    parser.add_argument('--port', type=int, default=4186)
    parser.add_argument('--extra-modules', type=int, default=0)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), PreviewHandler)
    server.roots = {name: getattr(args, name).resolve() / 'docs/.vitepress/dist' for name in ('portal', 'redis', 'langchain')}
    server.extra_modules = args.extra_modules
    print(f'http://127.0.0.1:{args.port}/', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
