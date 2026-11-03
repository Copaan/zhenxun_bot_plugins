import sys
from typing import ClassVar

from tortoise import fields

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:
    from strenum import StrEnum

from zhenxun.services.db_context import Model


class BankHandleType(StrEnum):
    DEPOSIT = "DEPOSIT"
    """存款"""
    WITHDRAW = "WITHDRAW"
    """取款"""
    LOAN = "LOAN"
    """贷款"""
    REPAYMENT = "REPAYMENT"
    """还款"""
    INTEREST = "INTEREST"
    """利息"""


class MahiroBankLog(Model):
    id = fields.IntField(pk=True, generated=True, auto_increment=True)
    """自增id"""
    user_id = fields.CharField(255, description="用户id")
    """用户id"""
    amount = fields.BigIntField(default=0, description="存款")
    """金币数量"""
    rate = fields.FloatField(default=0, description="小时利率")
    """小时利率"""
    handle_type = fields.CharEnumField(
        BankHandleType, null=True, description="处理类型"
    )
    """处理类型"""
    is_completed = fields.BooleanField(default=False, description="是否完成")
    """是否完成"""
    effective_hour = fields.IntField(default=0, description="有效小时")
    """有效小时"""
    update_time = fields.DatetimeField(auto_now=True)
    """修改时间"""
    create_time = fields.DatetimeField(auto_now_add=True)
    """创建时间"""

    class Meta:  # pyright: ignore [reportIncompatibleVariableOverride]
        table = "mahiro_bank_log"
        table_description = "小真寻银行日志"
        indexes: ClassVar = [
            ("user_id", "is_completed", "create_time"),
            ("user_id", "create_time"),
        ]
