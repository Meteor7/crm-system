import type { Locale } from '@/i18n'

// Display translations for the built-in catalog; persisted catalog and custom names stay intact.
const englishNames: Record<string, string> = {
  "Drakens 4482 宏观缺陷自动检测设备(6”/8”/12”)": "Drakens 4482 automatic macro defect inspection system (6”/8”/12”)",
  "检测腔体 Process module": "Process module",
  "晶圆传输系统 EFEM": "Wafer transfer system (EFEM)",
  "四通道时域照明系统": "Four-channel time-domain illumination system",
  "高分辨四通道采集系统": "High-resolution four-channel acquisition system",
  "自动缺陷检测系统及ADC分类系统": "Automatic defect inspection and ADC classification system",
  "高精度运动平台(含6”/8” adaptor)": "High-precision motion stage (including 6”/8” adaptor)",
  "结果查看器 Results viewer license": "Results viewer license",
  "FFU 洁净单元": "FFU clean unit",
  "离子棒": "Ionizing bar",
  "SECS GEM标准通讯协议": "SECS GEM standard communication protocol",
  "符合SEMI2、8标准": "Compliance with SEMI2 and SEMI8 standards",
  "class 10 洁净微环境": "Class 10 clean mini-environment",
  "机械手+两套手臂": "Robot with two sets of arms",
  "背面非接触式手指(8寸)": "Non-contact backside fingers (8 inch)",
  "背面非接触式手指(6寸)": "Non-contact backside fingers (6 inch)",
  "Load port（12寸/8寸/6寸兼容）": "Load port (12/8/6 inch compatible)",
  "边缘夹持晶圆对位系统(8寸)": "Edge-grip wafer alignment system (8 inch)",
  "边缘夹持晶圆对位系统(6寸)": "Edge-grip wafer alignment system (6 inch)",
  "EFEM兼容多个检测模块升级": "EFEM upgrade for compatibility with multiple inspection modules"
}

export function quotationCatalogLabel(name: string, locale: Locale) {
  return locale === 'en-US' ? englishNames[name] ?? name : name
}
