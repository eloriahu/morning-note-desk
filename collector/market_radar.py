"""Offline, provisional event triage for a broad public-news discovery queue.

The watchlist is an optional priority hint, never the discovery universe. Scores
rank textual event signals; they do not establish novelty, investment merit,
issuer identity, publication time, or whether a claim is true. Keep the original
headline and source even when this inexpensive first pass finds no event.
"""
from __future__ import annotations

import re
import unicodedata


def _normalise(value):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(value or ""))).strip()


def _pattern(value):
    return re.compile(value, re.IGNORECASE)


# Specific multiword signals are deliberate: "offer", "bid", "results", and
# "tender" on their own are not evidence of a securities or corporate event.
_RULES = (
    ("Tender/deadline", "Merger Arbitrage", 94, _pattern(
        r"\b(?:tender offer|takeover offer|public offer for (?:the )?shares|"
        r"offer (?:price|period)|squeeze[ -]out|TOB|MBO|go[ -]private|going private)\b"
        r"|(?<![A-Za-z])(?:TOB|MBO)(?![A-Za-z])|公開買付|公開買い付け|株式非公開化|非公開化|要約收購|要约收购|公開收購|公开收购"
        r"|oferta p[uú]blica de aquisi[çc][aã]o")),
    ("Deal terms/process", "Merger Arbitrage", 88, _pattern(
        r"\b(?:mergers?|acquisitions?|takeovers?|buyouts?|M\s*&\s*A|"
        r"merger agreement|scheme of arrangement|sale of (?:a |the |its )?(?:business|unit|subsidiary)|"
        r"strategic alternatives|strategic review|acquire[sd]?|acquiring)\b"
        r"|\b(?:buy[si]?|bought|purchase[sd]?)\s+(?:(?:its|a|the)\s+)?(?:rival|competitor|company|business|stake)\b"
        r"|(?<![A-Za-z])M\s*&\s*A(?![A-Za-z])|買収|合併|経営統合|事業売却|身売り|收購|收购|併購|并购|兼併|兼并|出售子公司"
        r"|\b(?:aquisi[çc][aã]o|fus[aã]o|incorpora[çc][aã]o)\b")),
    ("Restructuring/spin-off", "Fundamental/Pre-Event", 84, _pattern(
        r"\b(?:spin[ -]?offs?|demergers?|debt restructuring|corporate restructuring|"
        r"bankruptcy|chapter 11|receivership|insolvency|delisting|break[ -]up of)\b"
        r"|会社分割|事業再編|経営再建|民事再生|会社更生|上場廃止|スピンオフ|分拆上市|分拆|破產|破产|退市"
        r"|資產重組|资产重组|債務重組|债务重组|recupera[çc][aã]o judicial|cis[aã]o")),
    ("Ownership/activism", "Fundamental/Pre-Event", 80, _pattern(
        r"\b(?:activist (?:investor|fund|shareholder)|shareholder activism|proxy (?:fight|contest)|"
        r"(?:buys?|acquires?|raises?|increases?|cuts?|sells?|takes?|builds?)\s+(?:\w+\s+){0,5}stake|"
        r"(?:major|significant|controlling|minority|majority) (?:stake|shareholding)|"
        r"beneficial ownership|disclosure of interest|board challenge)\b"
        r"|アクティビスト|物言う株主|大量保有|株主提案|持ち分取得|持分取得|股東維權|股东维权"
        r"|增持股份|減持股份|减持股份|大股東增持|大股东增持|股權收購|股权收购"
        r"|investidor ativista|participa[çc][aã]o acion[aá]ria")),
    ("Buyback/capital return", "Fundamental/Pre-Event", 76, _pattern(
        r"\b(?:share buybacks?|stock buybacks?|buyback (?:program|programme)|"
        r"share repurchases?|stock repurchases?|special dividend|return of capital|"
        r"(?:raises?|cuts?|suspends?|increases?|reduces?) (?:its |the )?dividend|stock split|share split)\b"
        r"|自社株買い|自己株式取得|自己株式の取得|自己株式消却|増配|減配|無配|株式分割"
        r"|股份回購|股份回购|回購股份|回购股份|特別股息|特别股息|特別息|特别息|recompra de a[çc][oõ]es")),
    ("Results/guidance", "Fundamental/Pre-Event", 72, _pattern(
        r"\b(?:earnings|profit warning|profit forecast|revenue forecast|"
        r"(?:raises?|cuts?|lowers?|withdraws?|upgrades?|downgrades?) (?:its |the )?(?:guidance|outlook)|"
        r"(?:quarterly|annual|half[ -]year|full[ -]year|financial) results|"
        r"(?:net |operating )?profit (?:rises?|falls?|jumps?|drops?|surges?|slumps?)|"
        r"revenue (?:rises?|falls?|jumps?|drops?|surges?|slumps?))\b"
        r"|決算|業績予想|上方修正|下方修正|増益|減益|赤字転落|黒字転換|業績預告|业绩预告"
        r"|盈利預警|盈利预警|盈利警告|財報|财报|業績指引|业绩指引|純利益|純利潤|净利润"
        r"|resultados financeiros|lucro l[ií]quido")),
    ("Capital raising/IPO", "Fundamental/Pre-Event", 73, _pattern(
        r"\b(?:IPO|initial public offering|rights (?:issue|offering)|capital raising|"
        r"equity (?:raising|offering|placement)|share placement|private placement|"
        r"secondary offering|follow[ -]on offering|convertible bonds?|"
        r"(?:bond|debt) issuance|(?:issues?|sells?) (?:\w+\s+){0,4}(?:new shares|bonds))\b"
        r"|(?<![A-Za-z])IPO(?![A-Za-z])|新規上場|新規株式公開|公募増資|第三者割当|転換社債|起債|首次公開招股|首次公开招股"
        r"|配股|供股|增發|增发|可轉債|可转债|oferta inicial de a[çc][oõ]es")),
    ("Regulatory decision", "Fundamental/Pre-Event", 74, _pattern(
        r"\b(?:antitrust|competition (?:authority|regulator|clearance|probe)|"
        r"merger (?:clearance|approval|review)|FIRB|CFIUS|ACCC|"
        r"(?:regulator|regulators|court) (?:blocks?|approves?|clears?|fines?|rejects?)|"
        r"FDA (?:approves?|rejects?|clearance|approval)|securities fraud|class[ -]action lawsuit)\b"
        r"|独禁法|独占禁止法|公正取引委員会|企業結合審査|反壟斷|反垄断|經營者集中|经营者集中"
        r"|aprova[çc][aã]o do CADE|defesa da concorr[eê]ncia")),
)

_CORPORATE = _pattern(
    r"\b(?:companies|company|corporation|corp|holdings|plc|shareholders?|shares|stocks?|"
    r"equity|revenue|profits?|business|banks?|manufacturer|factory|factories|CEO|CFO|"
    r"billion|million|semiconductors?|chipmaker|retailer|investors?|funds?|subsidiary)\b"
    r"|[$€£¥]\s*\d|企業|株式会社|株式|株主|上場|売上高|営業利益|社長|金融|半導体|事業"
    r"|公司|股東|股东|股份|上市|股價|股价|營收|营收|企業|企业|董事|"
    r"\b(?:empresa|companhia|a[çc][oõ]es|lucro)\b")
_MACRO = _pattern(
    r"\b(?:inflation|interest rates?|central bank|federal reserve|GDP|bond yields?|"
    r"unemployment|currency|currencies|forex|oil prices?|gold prices?|tariffs?|"
    r"Nikkei index|Hang Seng|stock market|equity market|market rally)\b"
    r"|金利|金融政策|日銀|日本銀行|インフレ|為替|消費者物価|失業率|日経平均|"
    r"恒生指數|恒生指数|通脹|通胀|通縮|通缩|央行|貨幣政策|货币政策|關稅|关税|利率")

# Remove narrow non-corporate senses before looking for ambiguous M&A words.
# This does not suppress an actual takeover of a football club, for example.
_NONCORPORATE_ACQUISITION = _pattern(
    r"\b(?:language|skill|knowledge|data|image|signal) acquisition\b|"
    r"\bacquisition of (?:language|skills?|knowledge|data|images?|signals?)\b|"
    r"\b(?:black[ -]?hole|neutron[ -]?star|galaxy|galactic|stellar) mergers?\b|"
    r"\bmergers? of (?:black holes|neutron stars|galaxies)\b|"
    r"\b(?:acquire[sd]?|acquiring)\s+(?:new\s+)?(?:skills?|knowledge|language|immunity|infection)\b"
    r"|銀河合併|星系合併|星系合并|スキルの獲得")
_AMBIGUOUS_ACQUISITION = _pattern(r"\b(?:acquire[sd]?|acquiring|acquisitions?|incorpora[çc][aã]o)\b")
_PERSONAL_PURCHASE = _pattern(
    r"\b(?:museum|gallery|collector|collectors|tourist|tourists|student|students)\b.*"
    r"\b(?:painting|portrait|artwork|artworks|artifact|artefact|book|books|souvenir|souvenirs)\b")


def triage(title, text="", priority_matches=None):
    """Return provisional, explainable discovery priority without ticker inference.

    ``priority_matches`` may contain watchlist identifiers or names already
    matched by the caller. The values are never interpreted or returned as an
    inferred identity. No watchlist match is necessary to discover an event.
    Article text is optional; a body-only event signal receives a small discount
    because it can refer to background rather than the headline's main event.
    """
    headline = _normalise(title)
    body = _normalise(text)
    combined = " ".join((headline, body)).strip()
    financial_context = bool(_CORPORATE.search(combined))
    matched = []
    for event_type, category, base_score, expression in _RULES:
        in_title = headline
        in_body = body
        if event_type == "Deal terms/process":
            in_title = _NONCORPORATE_ACQUISITION.sub("", in_title)
            in_body = _NONCORPORATE_ACQUISITION.sub("", in_body)
            if _PERSONAL_PURCHASE.search(combined) and not financial_context:
                in_title = _AMBIGUOUS_ACQUISITION.sub("", in_title)
                in_body = _AMBIGUOUS_ACQUISITION.sub("", in_body)
        if expression.search(in_title):
            matched.append((base_score, event_type, category, "headline"))
        elif expression.search(in_body):
            matched.append((base_score - 8, event_type, category, "article text"))

    if matched:
        matched.sort(key=lambda item: item[0], reverse=True)
        score, event_type, category, _ = matched[0]
        reasons = [f"{kind} signal in {location}" for _, kind, _, location in matched[:3]]
        relevant = True
    elif _MACRO.search(combined):
        score, event_type, category = 24, "Macro/markets", "Other Strategy"
        reasons = ["Macro or market context; no specific corporate-event signal"]
        relevant = True
    elif financial_context:
        score, event_type, category = 18, "General business", "Other Strategy"
        reasons = ["General business context; no specific corporate-event signal"]
        relevant = True
    else:
        score, event_type, category = 0, "Other", "Other Strategy"
        reasons = ["No recognised corporate or market signal"]
        relevant = False

    if priority_matches:
        score += 8
        reasons.append("Priority-name match (+8); identity supplied by the caller")

    return {
        "attention_score": min(100, score),
        "attention_reasons": reasons,
        "event_type": event_type,
        "category": category,
        "market_relevant": relevant,
    }
