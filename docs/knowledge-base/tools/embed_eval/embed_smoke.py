# -*- coding: utf-8 -*-
"""Embedding service health smoke: embed one string via the production
path (WeKnora-app container -> weknora-ollama) and report dimension +
latency. Usage: python embed_smoke.py <ollama_model>"""
import subprocess
import sys
import time

model = sys.argv[1] if len(sys.argv) > 1 else "bge-m3:latest"
inner = r'''
import json,urllib.request,time,os
body=json.dumps({"model":os.environ["EMB_MODEL"],"input":["保险法第一条"]}).encode()
req=urllib.request.Request("http://weknora-ollama:11434/api/embed",
    data=body,headers={"Content-Type":"application/json"},method="POST")
t0=time.time()
with urllib.request.urlopen(req,timeout=60) as r:
    d=json.loads(r.read().decode())
v=d["embeddings"][0]
print(json.dumps({"dim":len(v),"elapsed_ms":int((time.time()-t0)*1000),
                  "model":d.get("model")}))
'''
r = subprocess.run(
    ["docker", "exec", "-e", "EMB_MODEL=" + model, "-i", "WeKnora-app",
     "python3", "-c", inner], capture_output=True, text=True, timeout=120)
print(model, "->", (r.stdout or r.stderr).strip())
