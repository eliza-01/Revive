# core/logging_setup.py
import os
import sys
import logging
import builtins

def init_logging():
    base = os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else __file__)
    log_path = os.path.join(base, 'revive.log')
    logging.basicConfig(filename=log_path, level=logging.INFO, format='%(asctime)s %(message)s')
    _print = builtins.print
    def print_proxy(*args, **kwargs):
        _print(*args, **kwargs)
        try:
            logging.info(" ".join(str(a) for a in args))
        except Exception:
            pass
    builtins.print = print_proxy
    return log_path
