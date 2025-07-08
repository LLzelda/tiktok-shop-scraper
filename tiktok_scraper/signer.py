import execjs, pathlib, urllib.parse as up, time, random

_JS = (pathlib.Path(__file__).parent / "js" / "signer.js").read_text()
_ctx = execjs.compile(_JS)

def sign(url: str, params: dict[str, str | int]):
    out = _ctx.call("sign", url, params)
    params.update(out)
    return url + "?" + up.urlencode(params)

def demo(): #just for testing
    base = "https://www.tiktok.com/api/shop/item_list/"
    qs = {
        "aid": 1988,
        "shop_id": "7130027812345678901",
        "count": 30,
        "cursor": 0,
        "timestamp": int(time.time()*1000),
        "device_id": random.randint(10**17, 10**18-1),
        "region": "US",
    }
    print(sign(base, qs))

if __name__ == "__main__":
    demo()