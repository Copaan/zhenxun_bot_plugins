import asyncio
import datetime
import json
from pathlib import Path

from bilibili_api import Credential as BilibiliCredential
from bilibili_api import dynamic as bilibili_dynamic_module
from bilibili_api import live as bilibili_live_module
from bilibili_api import user as bilibili_user_module
from zhenxun import ui
from zhenxun.configs.path_config import IMAGE_PATH
from zhenxun.services.log import logger
from zhenxun.utils.http_utils import AsyncHttpx

from .config import AVATAR_CACHE_DIR, BANGUMI_COVER_CACHE_DIR, get_credential

BORDER_PATH = IMAGE_PATH / "border"
BORDER_PATH.mkdir(parents=True, exist_ok=True)
BASE_URL = "https://api.bilibili.com"


async def get_pic(url: str) -> bytes:
    """获取图像"""
    return (await AsyncHttpx.get(url, timeout=10)).content


async def get_cached_avatar(uid: int, avatar_url: str) -> Path | None:
    """获取缓存的用户头像路径，如果不存在则下载"""
    if not avatar_url or not uid:
        return None
    cached_path = AVATAR_CACHE_DIR / f"{uid}.png"
    if cached_path.exists():
        logger.debug(f"头像缓存命中: UID {uid}")
        return cached_path

    logger.debug(f"头像缓存未命中，正在下载: UID {uid}")
    try:
        if await AsyncHttpx.download_file(avatar_url, cached_path):
            return cached_path
    except Exception as e:
        logger.error(f"下载头像失败 UID: {uid}, URL: {avatar_url}", e=e)
    return None


async def get_cached_bangumi_cover(season_or_ep_id: int, cover_url: str) -> Path | None:
    """获取缓存的番剧或剧集封面路径，如果不存在则下载"""
    if not cover_url or not season_or_ep_id:
        return None
    cached_path = BANGUMI_COVER_CACHE_DIR / f"{season_or_ep_id}.png"
    if cached_path.exists():
        logger.debug(f"番剧封面缓存命中: ID {season_or_ep_id}")
        return cached_path

    logger.debug(f"番剧封面缓存未命中，正在下载: ID {season_or_ep_id}")
    try:
        if await AsyncHttpx.download_file(cover_url, cached_path):
            return cached_path
    except Exception as e:
        logger.error(f"下载番剧封面失败 ID: {season_or_ep_id}, URL: {cover_url}", e=e)
    return None


async def get_videos(uid: int, auth: BilibiliCredential | None = None, **kwargs):
    """获取用户投搞视频信息"""
    credential = auth or get_credential()
    user_instance = bilibili_user_module.User(uid=uid, credential=credential)
    return await user_instance.get_videos(**kwargs)


async def get_user_card(
    mid: int, photo: bool = False, auth: BilibiliCredential | None = None, **kwargs
):
    """获取用户卡片信息"""
    credential = auth or get_credential()
    user_instance = bilibili_user_module.User(uid=mid, credential=credential)
    user_info = await user_instance.get_user_info()
    return user_info


async def get_user_dynamics(
    uid: int,
    offset: int = 0,
    need_top: bool = False,
    auth: BilibiliCredential | None = None,
    **kwargs,
):
    """获取指定用户历史动态"""
    credential = auth or get_credential()
    user_instance = bilibili_user_module.User(uid=uid, credential=credential)
    offset_str = "" if not offset else str(offset)
    dynamics = await user_instance.get_dynamics_new(offset=offset_str, **kwargs)
    if not dynamics.get("items"):
        await asyncio.sleep(0.5)
        dynamics = await user_instance.get_dynamics_new(offset=offset_str, **kwargs)
    return _convert_new_dynamics_to_old_cards(dynamics, need_top=need_top)


def _convert_new_dynamics_to_old_cards(dynamics: dict, need_top: bool = False) -> dict:
    """将新版动态接口 items 转为插件既有的 cards 结构。"""
    if not isinstance(dynamics, dict):
        return {"cards": []}

    cards = []
    for item in dynamics.get("items", []) or []:
        if not need_top and _is_top_dynamic(item):
            continue
        card = _convert_new_dynamic_item(item)
        if card:
            cards.append(card)

    return {
        "cards": cards,
        "has_more": dynamics.get("has_more", False),
        "next_offset": dynamics.get("offset", ""),
        "offset": dynamics.get("offset", ""),
    }


def _convert_new_dynamic_item(item: dict) -> dict | None:
    if not isinstance(item, dict):
        return None

    modules = item.get("modules") or {}
    author = modules.get("module_author") or {}
    dynamic = modules.get("module_dynamic") or {}
    major = dynamic.get("major") or {}
    additional = dynamic.get("additional") or {}

    dynamic_id = item.get("id_str") or item.get("id")
    timestamp = author.get("pub_ts") or 0
    try:
        timestamp = int(timestamp)
    except (TypeError, ValueError):
        timestamp = 0

    text_parts = []
    desc = dynamic.get("desc") or {}
    if isinstance(desc, dict) and desc.get("text"):
        text_parts.append(desc["text"])

    title, summary_text = _extract_major_text(major)
    if title:
        text_parts.append(title)
    if summary_text:
        text_parts.append(summary_text)

    images = _extract_major_images(major)
    item_data = {
        "description": "\n".join(part for part in text_parts if part),
        "content": "\n".join(part for part in text_parts if part),
        "pictures": [{"img_src": url} for url in images],
    }
    if images:
        item_data["pic"] = images[0]

    card_data = {
        "item": item_data,
        "user": {"description": item_data["description"]},
        "_new_dynamic": item,
    }
    if additional:
        card_data["additional"] = additional
        additional_type = additional.get("type") if isinstance(additional, dict) else ""
        if additional_type and "goods" in str(additional_type).lower():
            card_data["goods"] = additional

    return {
        "desc": {
            "timestamp": timestamp,
            "dynamic_id": dynamic_id,
            "type": _map_new_dynamic_type(item.get("type"), major, additional),
        },
        "card": card_data,
        "extend_json": {},
    }


def _is_top_dynamic(item: dict) -> bool:
    modules = item.get("modules") or {}
    author = modules.get("module_author") or {}
    tag = modules.get("module_tag") or {}
    return bool(author.get("is_top") or tag.get("text") == "置顶")


def _extract_major_text(major: dict) -> tuple[str, str]:
    if not isinstance(major, dict):
        return "", ""

    for key in ("opus", "draw", "article", "archive", "common"):
        data = major.get(key)
        if not isinstance(data, dict):
            continue

        title = data.get("title") or ""
        summary = data.get("summary") or {}
        if isinstance(summary, dict):
            summary_text = summary.get("text") or ""
        else:
            summary_text = str(summary) if summary else ""

        desc = data.get("desc") or ""
        text = summary_text or desc
        if title or text:
            return str(title), str(text)

    return "", ""


def _extract_major_images(major: dict) -> list[str]:
    if not isinstance(major, dict):
        return []

    images = []
    for key in ("opus", "draw"):
        data = major.get(key)
        if not isinstance(data, dict):
            continue

        pics = data.get("pics") or data.get("items") or []
        if isinstance(pics, dict):
            pics = [pics]
        for pic in pics:
            if not isinstance(pic, dict):
                continue
            url = pic.get("url") or pic.get("src") or pic.get("img_src")
            if url:
                images.append(url)

    return images


def _map_new_dynamic_type(
    dynamic_type: str | None, major: dict, additional: dict | None = None
) -> int:
    if additional and isinstance(additional, dict):
        additional_type = str(additional.get("type") or "").lower()
        if "goods" in additional_type:
            return 19

    major_type = str((major or {}).get("type") or "").upper()
    if "ARTICLE" in major_type:
        return 64

    type_map = {
        "DYNAMIC_TYPE_DRAW": 2,
        "DYNAMIC_TYPE_AV": 8,
        "DYNAMIC_TYPE_FORWARD": 1,
        "DYNAMIC_TYPE_ARTICLE": 64,
    }
    return type_map.get(str(dynamic_type or ""), 0)


async def get_room_info_by_id(
    live_id: int, auth: BilibiliCredential | None = None, **kwargs
):
    """根据房间号获取指定直播间信息"""
    credential = auth or get_credential()
    liveroom_instance = bilibili_live_module.LiveRoom(
        room_display_id=live_id, credential=credential
    )
    return await liveroom_instance.get_room_info()


DYNAMIC_MAX_IMAGES = 9
"""动态卡片最多展示的图片数"""
TEMPLATE_PATH = Path(__file__).parent / "templates" / "dynamic_card.html"


def _https(url: str) -> str:
    return f"https:{url}" if url.startswith("//") else url


def _rich_runs(nodes: list[dict] | None) -> list[dict]:
    """把动态富文本节点转为卡片文字片段

    参数:
        nodes: 富文本节点

    返回:
        list[dict]: 文字片段，含 text、link 或 emoji
    """
    runs = []
    for node in nodes or []:
        node_type = node.get("type", "")
        if node_type == "RICH_TEXT_NODE_TYPE_EMOJI" and node.get("emoji"):
            runs.append({"emoji": _https(node["emoji"].get("icon_url", ""))})
        else:
            runs.append(
                {
                    "text": node.get("text", ""),
                    "link": node_type != "RICH_TEXT_NODE_TYPE_TEXT",
                }
            )
    return runs


def build_dynamic_card(item: dict) -> dict:
    """把动态详情整理为动态卡片模板数据，转发动态的原动态放在 orig 中

    参数:
        item: 动态详情接口返回的 item

    返回:
        dict: 作者、文字、图片、视频等卡片内容
    """
    modules = item.get("modules") or {}
    author = modules.get("module_author") or {}
    dynamic = modules.get("module_dynamic") or {}
    major = dynamic.get("major") or {}
    card: dict = {
        "author": {
            "name": author.get("name", ""),
            "face": _https(author.get("face", "")),
            "time": author.get("pub_time", ""),
            "action": author.get("pub_action", ""),
        },
        "title": "",
        "runs": _rich_runs((dynamic.get("desc") or {}).get("rich_text_nodes")),
        "images": [],
        "video": None,
        "link": None,
        "orig": None,
    }
    major_type = major.get("type", "")
    if major_type == "MAJOR_TYPE_OPUS":
        opus = major.get("opus") or {}
        card["title"] = opus.get("title") or ""
        card["runs"] += _rich_runs((opus.get("summary") or {}).get("rich_text_nodes"))
        card["images"] = [_https(p["url"]) for p in opus.get("pics") or []]
    elif major_type == "MAJOR_TYPE_DRAW":
        items = (major.get("draw") or {}).get("items") or []
        card["images"] = [_https(i["src"]) for i in items]
    elif major_type == "MAJOR_TYPE_ARCHIVE":
        archive = major.get("archive") or {}
        stat = archive.get("stat") or {}
        card["video"] = {
            "cover": _https(archive.get("cover", "")),
            "title": archive.get("title", ""),
            "desc": archive.get("desc", ""),
            "duration": archive.get("duration_text", ""),
            "play": stat.get("play", ""),
            "danmaku": stat.get("danmaku", ""),
        }
    elif major_type == "MAJOR_TYPE_LIVE_RCMD":
        try:
            live = json.loads((major.get("live_rcmd") or {}).get("content", "{}"))
        except ValueError:
            live = {}
        info = live.get("live_play_info") or {}
        card["link"] = {
            "cover": _https(info.get("cover", "")),
            "title": info.get("title", ""),
            "desc": "直播中" if info.get("live_status") == 1 else "",
        }
    elif major_type == "MAJOR_TYPE_NONE":
        tips = (major.get("none") or {}).get("tips") or "源动态已被删除"
        card["runs"] += [{"text": tips}]
    elif major_type:
        key = major_type.removeprefix("MAJOR_TYPE_").lower()
        data = major.get(key) or {}
        covers = data.get("covers") or [data.get("cover", "")]
        card["link"] = {
            "cover": _https(covers[0] if covers else ""),
            "title": data.get("title", ""),
            "desc": data.get("desc") or data.get("desc1") or "",
        }
    card["images"] = card["images"][:DYNAMIC_MAX_IMAGES]
    if orig := item.get("orig"):
        card["orig"] = build_dynamic_card(orig)
    stat = modules.get("module_stat") or {}
    card["stat"] = {
        key: (stat.get(key) or {}).get("count", 0)
        for key in ("like", "comment", "forward")
    }
    return card


async def render_dynamic_card(dynamic_id: int) -> bytes | None:
    """获取动态详情并渲染为动态卡片

    参数:
        dynamic_id: 动态 ID

    返回:
        bytes | None: 卡片图片，动态不存在或获取失败时为 None
    """
    try:
        data = await bilibili_dynamic_module.Dynamic(
            dynamic_id, credential=get_credential()
        ).get_info()
        card = build_dynamic_card(data["item"])
        component = ui.template(TEMPLATE_PATH, data=card)
        return await ui.render(component, viewport={"width": 640, "height": 10})
    except Exception as e:
        logger.warning(f"动态卡片生成失败: {dynamic_id}", e=e)
    return None


def calc_time_total(t: float):
    """计算人类可读格式的总时间"""
    if not isinstance(t, (int, float)):
        try:
            t = float(t)
        except (ValueError, TypeError):
            return "时间格式错误"

    t_int = int(t * 1000)
    if t_int < 5000:
        return f"{t_int} 毫秒"
    timedelta_obj = datetime.timedelta(seconds=t_int // 1000)
    day = timedelta_obj.days
    hour, mint, sec = tuple(
        int(n) for n in str(timedelta_obj).split(",")[-1].split(":")
    )
    total = ""
    if day:
        total += f"{day} 天 "
    if hour:
        total += f"{hour} 小时 "
    if mint:
        total += f"{mint} 分钟 "
    if sec and not day and not hour:
        total += f"{sec} 秒 "
    return total.strip()
