#!/usr/bin/env python3
"""Send image(s) + a question to the local Qwen3.8-27B (vision via mmproj)
and print the model's answer.

Usage:
  python3 ask_vision.py "your question" img1.png [img2.png ...]
  python3 ask_vision.py -q "question" -p 8080 img.png
"""
import base64, json, os, sys, urllib.request

def b64(path):
    with open(path, 'rb') as f:
        return base64.b64encode(f.read()).decode()

def call(base_url, model, question, images, max_tokens=4000, api_key=""):
    content = [{"type": "text", "text": question}]
    for im in images:
        content.append({"type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64(im)}"}})
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": max_tokens,
        "temperature": 0.2,
    }).encode()
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(
        base_url + "/v1/chat/completions",
        data=payload,
        headers=headers)
    with urllib.request.urlopen(req, timeout=900) as r:
        data = json.load(r)
    return data["choices"][0]["message"]["content"]

def main():
    args = sys.argv[1:]
    port = 8080
    model = "local-model"
    api_key = os.environ.get("LLM_API_KEY", "")
    q = None
    max_tokens = 4000
    imgs = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "-p":
            port = int(args[i + 1]); i += 2; continue
        if a == "-m":
            model = args[i + 1]; i += 2; continue
        if a == "-k":
            api_key = args[i + 1]; i += 2; continue
        if a == "-q":
            q = args[i + 1]; i += 2; continue
        if a == "-t":
            max_tokens = int(args[i + 1]); i += 2; continue
        imgs.append(a)
        i += 1
    if q is None:
        if not imgs:
            print("usage: ask_vision.py [question] imgs...  (-q for question)"); sys.exit(2)
        q, imgs = imgs[0], imgs[1:]
    try:
        print(call(f"http://127.0.0.1:{port}", model, q, imgs,
                   max_tokens=max_tokens, api_key=api_key))
    except Exception as e:
        # fall back: model name may differ; fetch /v1/models
        print(f"direct call failed ({e}); listing models...", file=sys.stderr)
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/v1/models", timeout=30) as r:
            models = json.load(r)
        name = models["data"][0]["id"]
        print(call(f"http://127.0.0.1:{port}", name, q, imgs,
                   max_tokens=max_tokens, api_key=api_key))

if __name__ == "__main__":
    main()
