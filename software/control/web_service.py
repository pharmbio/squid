from dataclasses import dataclass, field
import typing as t
from threading import Thread, Lock
from flask import Flask, request, jsonify
from queue import Queue
import inspect
import json
import functools

import qtpy.QtCore as QtCore
Signal: 't.Type[QtCore.pyqtSignal]' = QtCore.Signal # type: ignore

class RemoteCall(QtCore.QObject):
    remote_call_signal = Signal(dict)

def try_json_loads(s: str) -> t.Any:
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return s

def json_or_repr(x: t.Any) -> t.Any:
    if isinstance(x, dict):
        return {str(k): json_or_repr(v) for k, v in t.cast(t.Dict[t.Any, t.Any], x).items()}
    try:
        json.dumps(x)
        return x
    except:
        return repr(x)

@dataclass(frozen=True)
class WebService:
    exposed: t.Dict[str, t.Callable[[t.Dict[str, t.Any]], t.Any]] = field(default_factory=dict)
    lock: Lock = field(default_factory=Lock)
    status: t.Dict[str, t.Any] = field(default_factory=dict)

    def set_status(self, **kws: t.Any):
        self.status.update(kws)

    def start(self, host: str = 'localhost', port: int = 4321, namespace: str = 'squid'):
        self.expose(lambda: self.status, name='status')

        app = Flask(__name__)
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True # type: ignore
        app.config['JSON_SORT_KEYS'] = False             # type: ignore

        def call_with_args(method: str, *args: t.Any, **kwargs: t.Any):
            with self.lock:
                print(method, kwargs)
                return jsonify(json_or_repr(self.exposed[method](kwargs)))

        @app.get(f'/{namespace}/<method>')
        def call(method: str):
            kwargs = {k: try_json_loads(v) for k, v in request.args.items()}
            return call_with_args(method, **kwargs)

        @app.post(f'/{namespace}')
        def post():
            # compability with pharmbio/robotlab/labrobots
            req = request.json
            assert req
            cmd = req['cmd']
            args = req['args']
            kwargs = req['kwargs']
            res = call_with_args(cmd, *args, **kwargs)
            if isinstance(res, dict) and '_error' in res:
                return res
            else:
                return {'value': res}

        @app.get('/')
        def help():
            def try_signature(fn: t.Any):
                try:
                    return str(inspect.signature(fn))
                except:
                    return ''
            return jsonify({f'{namespace}/{k}': v.__qualname__ + try_signature(v) for k, v in self.exposed.items()})

        def main():
            app.run(host, port, threaded=True, processes=1)

        Thread(target=main, daemon=True).start()

    def expose(self, fn: t.Callable[..., t.Any], name: t.Union[str, None] = None):
        k = name or fn.__name__
        s = RemoteCall()

        @functools.wraps(fn)
        def connected_fun(kwargs: t.Dict[str, t.Any]):
            reply_q: 'Queue[t.Any]' = kwargs.pop('_reply_q')
            try:
                res = fn(**kwargs)
            except BaseException as e:
                import traceback as tb
                res = {'_error': str(e), '_traceback': tb.format_exc().splitlines()}
                tb.print_exc()
            reply_q.put_nowait(res)

        @functools.wraps(fn)
        def exposed_fn(kwargs: t.Dict[str, t.Any]):
            reply_q: 'Queue[t.Any]' = Queue()
            kwargs.update(_reply_q=reply_q)
            s.remote_call_signal.emit(kwargs)
            return reply_q.get()

        s.remote_call_signal.connect(connected_fun)
        with self.lock:
            self.exposed[k] = exposed_fn

web_service = WebService()
