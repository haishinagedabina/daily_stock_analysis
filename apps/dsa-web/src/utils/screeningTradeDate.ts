const SHANGHAI_TIMEZONE = 'Asia/Shanghai';
const CN_MARKET_CLOSE_HOUR = 15;

function getShanghaiParts(now: Date) {
  const formatter = new Intl.DateTimeFormat('en-CA', {
    timeZone: SHANGHAI_TIMEZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });

  const partMap = new Map(
    formatter
      .formatToParts(now)
      .filter((part) => part.type !== 'literal')
      .map((part) => [part.type, part.value]),
  );

  return {
    date: `${partMap.get('year')}-${partMap.get('month')}-${partMap.get('day')}`,
    hour: Number(partMap.get('hour') ?? '0'),
  };
}

export function getTodayInShanghai(now: Date = new Date()): string {
  return getShanghaiParts(now).date;
}

export function shouldBlockTodayScreening(tradeDate?: string, now: Date = new Date()): boolean {
  if (!tradeDate) {
    return false;
  }

  const snapshot = getShanghaiParts(now);
  return tradeDate === snapshot.date && snapshot.hour < CN_MARKET_CLOSE_HOUR;
}

export function buildTodayScreeningBlockDialog(tradeDate?: string, now: Date = new Date()) {
  if (!shouldBlockTodayScreening(tradeDate, now)) {
    return null;
  }

  return {
    title: '今日数据未就绪',
    message:
      '当前时间未到 15:00（Asia/Shanghai），今日 A 股日线数据未完全收盘，请选择上一交易日或 15:00 后再试。',
  };
}
