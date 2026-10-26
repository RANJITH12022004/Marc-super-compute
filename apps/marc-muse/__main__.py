"""Run marc-muse:  python apps/marc-muse/server.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from server import serve

if __name__ == "__main__":
    serve()
