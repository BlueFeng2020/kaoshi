"""Auditable local vocabulary; rules never depend on row IDs or expected anomaly counts.

Exact phrases describe a likely category, not a confirmed diagnosis. A contradiction
is retained for review and grouped as 未分类 rather than silently changing its type.
Unseen or ambiguous descriptions do not trigger an inferred correction.
"""
DESCRIPTION_TYPES = {
    '机械故障': ['丝杠间隙过大','主轴异响、振动加剧','传动皮带断裂','联轴器损坏','轴承温度过高烧蚀','齿轮磨损打齿'],
    '电气故障': ['接触器触点烧毁','断路器跳闸频繁','电机绕组烧毁','端子排松动发热','线路绝缘老化短路'],
    '控制/软件故障': ['PLC程序异常停机','伺服报警代码无法复位','参数丢失无法启动','触摸屏黑屏','通信中断报警'],
    '液压故障': ['油泵压力不足','油缸密封泄漏','油路堵塞','液压油乳化变质','溢流阀卡滞'],
    '气动故障': ['气动三联件堵塞','气源压力波动','气管破损漏气','气缸动作缓慢','电磁阀卡滞'],
    '磨损老化': ['密封件老化渗漏','导轨磨损精度下降','易损件到期磨损','滤芯堵塞压差高','皮带老化龟裂'],
    '外部因素': ['异物进入设备','操作不当误动作','电压波动致停机','突发停电','雷击损坏模块'],
    '润滑问题': ['油质劣化发黑','油路分配器堵塞','润滑泵不工作','缺油导致温升'],
    '其他': ['外观损伤影响使用','振动超标','设备异响待查','跑冒滴漏'],
}
DESCRIPTION_LOOKUP = {phrase:category for category,phrases in DESCRIPTION_TYPES.items() for phrase in phrases}


def expected_fault_type(description):
    return DESCRIPTION_LOOKUP.get(str(description).strip())
