from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Alconna, Args, Arparma, Match, on_alconna
from nonebot_plugin_session import EventSession
from zhenxun.configs.utils import Command, PluginExtraData
from zhenxun.services.log import logger
from zhenxun.utils.message import MessageUtils

from .data_source import get_hot_image

__plugin_meta__ = PluginMetadata(
    name="微博热搜",
    description="刚买完瓜，在吃瓜现场",
    usage="""
    指令：
        微博热搜：发送实时热搜
        微博热搜 [id]：发送该热搜的链接
        示例：微博热搜 5
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier & yajiwa",
        version="0.3",
        commands=[Command(command="微博热搜 ?[id]")],
    ).to_dict(),
)


_matcher = on_alconna(Alconna("微博热搜", Args["idx?", int]), priority=5, block=True)


@_matcher.handle()
async def _(session: EventSession, arparma: Arparma, idx: Match[int]):
    result, data_list = await get_hot_image()
    if isinstance(result, str):
        await MessageUtils.build_message(result).finish(reply_to=True)
    if idx.available:
        _idx = idx.result
        if not 0 < _idx <= len(data_list):
            await MessageUtils.build_message(
                f"热搜序号需在 1~{len(data_list)} 之间..."
            ).finish(reply_to=True)
        data = data_list[_idx - 1]
        await MessageUtils.build_message(
            f"{_idx}. {data['hot_word']}\n{data['url']}"
        ).send()
        logger.info(f"查询微博热搜 Id: {_idx}", arparma.header_result, session=session)
    else:
        await MessageUtils.build_message(result).send()
        logger.info("查询微博热搜", arparma.header_result, session=session)
