from io import BytesIO

from nonebot.adapters import Bot, Event
from nonebot.typing import T_State
from nonebot_plugin_alconna import At as alcAt
from nonebot_plugin_alconna import Text as alcText
from nonebot_plugin_alconna import UniMsg
from nonebot_plugin_session import EventSession
from PIL import Image
from zhenxun.services.log import logger
from zhenxun.utils.http_utils import AsyncHttpx

from ._data_source import get_img_and_at_list
from ._model import WordBank


def _image_hash(content: bytes) -> str:
    """计算图片的平均哈希

    参数:
        content: 图片数据

    返回:
        str: 16 位十六进制哈希值
    """
    with Image.open(BytesIO(content)) as image:
        gray = image.convert("L").resize((8, 8), Image.Resampling.LANCZOS)
    pixels = list(gray.tobytes())
    mean = sum(pixels) / len(pixels)
    bits = "".join("1" if pixel > mean else "0" for pixel in pixels)
    return f"{int(bits, 2):016x}"


async def check(
    bot: Bot,
    event: Event,
    message: UniMsg,
    session: EventSession,
    state: T_State,
) -> bool:
    text = message.extract_plain_text().strip()
    img_list, at_list = get_img_and_at_list(message)
    problem = text
    if not text and len(img_list) == 1:
        try:
            r = await AsyncHttpx.get(img_list[0])
            problem = _image_hash(r.content)
        except Exception as e:
            logger.warning("获取图片失败", "词条检测", session=session, e=e)
    if at_list:
        temp = ""
        # TODO: 支持更多消息类型
        for msg in message:
            if isinstance(msg, alcAt):
                temp += f"[at:{msg.target}]"
            elif isinstance(msg, alcText):
                temp += msg.text
        problem = temp
    if event.is_tome() and bot.config.nickname:
        if isinstance(message[0], alcAt) and message[0].target == bot.self_id:
            problem = f"[at:{bot.self_id}]{problem}"
        elif problem and bot.config.nickname:
            nickname = [nk for nk in bot.config.nickname if str(message).startswith(nk)]
            problem = nickname[0] + problem if nickname else problem
    if not problem:
        return False
    match_entry = await WordBank.match_entry(session.id3 or session.id2, problem)
    if match_entry is not None:
        state["problem"] = problem  # type: ignore
        state["word_bank_match"] = match_entry  # type: ignore
        return True
    return False
