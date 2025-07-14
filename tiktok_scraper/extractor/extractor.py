from bs4 import BeautifulSoup, Tag
import re
import json
from pprint import pprint


def extract_router_data(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    script_tag = soup.find("script", id="__MODERN_ROUTER_DATA__")
    if not script_tag:
        raise ValueError("Router data script tag not found")
    try:
        script_content = script_tag.get_text()
        if not script_content:
            raise ValueError("Router data script tag is empty")
        router_data = json.loads(script_content)
        return router_data["loaderData"]["shop/pdp/(product_name_slug$)/(product_id)/page"]
    except Exception as e:
        raise ValueError(f"Failed to parse router_data: {e}")

def safe_get(obj, path: str):
    """
    安全访问嵌套字段
    path 例如: "component_data.product_info.shipping.logistics[0].shipping_fee.price_val"
    """
    try:
        parts = path.split('.')
        for part in parts:
            if '[' in part and ']' in part:
                # e.g. logistics[0]
                field, idx = part[:-1].split('[')
                obj = obj[field][int(idx)]
            else:
                obj = obj[part]
        return obj
    except Exception:
        return None

# ✅
def extract_product_fields(router_data: dict, html: str) -> dict:
    try:
        # 找到 "product_info" 组件
        component_list = router_data.get("page_config", {}).get("components_map", [])
        product_info_component = next(
            (c for c in component_list if c.get("component_name") == "product_info"),
            None
        )
        if not product_info_component:
            print("[extract_product_fields] Error: product_info component not found")
            return {}

        # 定义 helper 函数
        def safe_get(obj, path: str):
            try:
                parts = path.split('.')
                for part in parts:
                    if '[' in part and ']' in part:
                        key, idx = part[:-1].split('[')
                        obj = obj[key][int(idx)]
                    else:
                        obj = obj[part]
                return obj
            except Exception:
                return None

        # 提取字段
        seller_id = safe_get(product_info_component, "component_data.product_info.seller_id")
        shipping_price = safe_get(product_info_component, "component_data.product_info.shipping.logistics[0].shipping_fee.price_val")
        default_sku_id = safe_get(product_info_component, "component_data.product_info.default_sku_id")

        return {
            "seller_id": seller_id,
            "shipping_price": shipping_price,
            "default_sku_id": default_sku_id,
        }

    except Exception as e:
        print(f"[extract_product_fields] Error: {e}")
        return {}

# ✅
def extract_product_and_category_info(router_data: dict) -> dict:
    result = {
        "product_id": None,
        "seller_id": None,
        "seller_name": None,
        "seller_item_count": None,
        "title": None,
        "sales": None,
        "categories": [],
    }

    # 定位到 component_name == "product_info"
    components = router_data.get("page_config", {}).get("components_map", [])
    for comp in components:
        if comp.get("component_name") == "product_info":
            data = comp.get("component_data", {})

            # 提取 categories
            for cat in data.get("categories", []):
                result["categories"].append({
                    "category_id": cat.get("category_id"),
                    "level": cat.get("level"),
                    "parent_id": cat.get("parent_id"),
                    "category_name": cat.get("category_name")
                })

            # 提取 product_info 下的 product_id, seller, product_base
            prod_info = data.get("product_info", {})
            result["product_id"] = prod_info.get("product_id")

            seller = prod_info.get("seller", {})
            result["seller_id"] = seller.get("seller_id")
            result["seller_name"] = seller.get("name")
            result["seller_item_count"] = seller.get("product_count")

            product_base = prod_info.get("product_base", {})
            result["title"] = product_base.get("title")
            result["sales"] = product_base.get("sold_count")

            break  # 找到就退出 loop

    return result

def extract_sale_props(router_data: dict) -> list[dict]:
    # 找到 "product_info" 组件
    components = router_data.get("page_config", {}).get("components_map", [])
    for comp in components:
        if comp.get("component_name") == "product_info":
            product_info = comp.get("component_data", {}).get("product_info", {})
            sale_props = product_info.get("sale_props", [])

            result = []
            for prop in sale_props:
                values = []
                for val in prop.get("sale_prop_values", []):
                    values.append({
                        "prop_value_id": val.get("prop_value_id"),
                        "prop_value": val.get("prop_value")
                    })

                result.append({
                    "prop_id": prop.get("prop_id"),
                    "prop_name": prop.get("prop_name"),
                    "sale_prop_values": values
                })

            return result
    return []

def extract_skus(router_data: dict) -> list[dict]:
    components = router_data.get("page_config", {}).get("components_map", [])
    for comp in components:
        if comp.get("component_name") == "product_info":
            product_info = comp.get("component_data", {}).get("product_info", {})
            skus = product_info.get("skus", [])

            result = []
            for sku in skus:
                # 提取 sku_sale_props 结构
                sale_props = sku.get("sku_sale_props", [])
                prop_list = [{
                    "prop_id": p.get("prop_id"),
                    "prop_name": p.get("prop_name"),
                    "prop_value_id": p.get("prop_value_id"),
                    "prop_value": p.get("prop_value")
                } for p in sale_props]

                # 提取价格信息
                price_info = sku.get("price", {})
                real_price_val = price_info.get("real_price", {}).get("price_val")
                original_price_val = price_info.get("original_price_value")

                result.append({
                    "sku_id": sku.get("sku_id"),
                    "sku_sale_props": prop_list,
                    "sale_prop_value_ids": sku.get("sale_prop_value_ids"),
                    "stock": sku.get("stock"),
                    "low_stock_warning": sku.get("low_stock_warning"),  # 可为空
                    "price": {
                        "real_price_val": float(real_price_val) if real_price_val else None,
                        "original_price_value": float(original_price_val) if original_price_val else None
                    }
                })

            return result
    return []

def extract_review_info(router_data: dict) -> dict:
    components = router_data.get("page_config", {}).get("components_map", [])
    for comp in components:
        if comp.get("component_name") == "product_info":
            component_data = comp.get("component_data", {})
            # print("\n[DEBUG] component_data keys:", component_data.keys())
            product_info = component_data.get("product_info", {})
            # print("[DEBUG] product_info keys:", product_info.keys())

            review_info = product_info.get("product_detail_review", {})
            return {
                "product_rating": review_info.get("product_rating"),
                "review_count": review_info.get("review_count"),
            }
    return {
        "product_rating": None,
        "review_count": None,
    }


# def extract_title(html: str) -> str | None:
#     soup = BeautifulSoup(html, "lxml")

#     # 尝试提取 og:title
#     meta_tag = soup.find("meta", attrs={"property": "og:title"})
#     if meta_tag and isinstance(meta_tag, Tag):
#         content = meta_tag.get("content")
#         if content and isinstance(content, str):
#             return content.strip()


#     return None

# def extract_cover_img_url(html: str) -> str | None:
#     soup = BeautifulSoup(html, "lxml")
#     meta_tag = soup.find("meta", attrs={"property": "og:image"})
#     if meta_tag and isinstance(meta_tag, Tag):
#         content = meta_tag.get("content")
#         if content and isinstance(content, str):
#             return content.strip()
#     return None



with open("tiktok_scraper/extractor/sample_product.html", "r", encoding="utf-8") as f:
    html = f.read()


router_data = extract_router_data(html)
# product_info = extract_product_fields(router_data, html)
# pprint(product_info)
# category_info = extract_product_and_category_info(router_data)
# pprint(category_info)
# sale_props = extract_sale_props(router_data)
# pprint(sale_props)
# sku = extract_skus(router_data)
# pprint(sku)
review_info = extract_review_info(router_data)
pprint(review_info)





