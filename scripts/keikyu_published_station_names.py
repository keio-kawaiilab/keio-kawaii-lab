"""Pure station-name mapping shared by PDF extraction and runtime validation."""
from keikyu_official_train_evidence import norm

STATION_LABELS: dict[str, tuple[str, ...]] = {
    '.Sengakuji': ('泉岳寺',), '.Shinagawa': ('品川',), '.Kitashinagawa': ('北品川',),
    '.Shimbamba': ('新馬場',), '.AomonoYokocho': ('青物横丁',), '.Samezu': ('鮫洲',),
    '.Tachiaigawa': ('立会川',), '.Omorikaigan': ('大森海岸',), '.Heiwajima': ('平和島',),
    '.Omorimachi': ('大森町',), '.Umeyashiki': ('梅屋敷',), '.KeikyuKamata': ('京急蒲田',),
    '.Zoshiki': ('雑色',), '.Rokugodote': ('六郷土手',), '.KeikyuKawasaki': ('京急川崎',),
    '.HatchoNawate': ('八丁畷',), '.TsurumiIchiba': ('鶴見市場',), '.KeikyuTsurumi': ('京急鶴見',),
    '.Kagetsusojiji': ('花月総持寺',), '.Namamugi': ('生麦',), '.KeikyuShinkoyasu': ('京急新子安',),
    '.Koyasu': ('子安',), '.KanagawaShimmachi': ('神奈川新町',),
    '.KeikyuHigashikanagawa': ('京急東神奈川',), '.Kanagawa': ('神奈川',), '.Yokohama': ('横浜',),
    '.Tobe': ('戸部',), '.Hinodecho': ('日ノ出町',), '.Koganecho': ('黄金町',),
    '.Minamiota': ('南太田',), '.Idogaya': ('井土ヶ谷',), '.Gumyoji': ('弘明寺',),
    '.Kamiooka': ('上大岡',), '.Byobugaura': ('屛風浦', '屏風浦'), '.Sugita': ('杉田',),
    '.KeikyuTomioka': ('京急富岡',), '.Nokendai': ('能見台',), '.KanazawaBunko': ('金沢文庫',),
    '.KanazawaHakkei': ('金沢八景',), '.Oppama': ('追浜',), '.KeikyuTaura': ('京急田浦',),
    '.Anjinzuka': ('安針塚',), '.Hemi': ('逸見',), '.Shioiri': ('汐入',),
    '.YokosukaChuo': ('横須賀中央',), '.Kenritsudaigaku': ('県立大学',), '.Horinouchi': ('堀ノ内',),
    '.KeikyuOtsu': ('京急大津',), '.Maborikaigan': ('馬堀海岸',), '.Uraga': ('浦賀',),
    '.Kojiya': ('糀谷',), '.Otorii': ('大鳥居',), '.AnamoriInari': ('穴守稲荷',),
    '.Tenkubashi': ('天空橋',), '.HanedaAirportTerminal3': ('羽田空港第3ターミナル', '羽田空港第３ターミナル'),
    '.HanedaAirportTerminal1and2': ('羽田空港第1・第2ターミナル', '羽田空港第１・第２ターミナル'),
    '.Shinotsu': ('新大津',), '.Kitakurihama': ('北久里浜',), '.KeikyuKurihama': ('京急久里浜',),
    '.YrpNobi': ('YRP野比', 'ＹＲＰ野比'), '.KeikyuNagasawa': ('京急長沢',),
    '.Tsukuihama': ('津久井浜',), '.Miurakaigan': ('三浦海岸',), '.Misakiguchi': ('三崎口',),
    '.Mutsuura': ('六浦',), '.Jimmuji': ('神武寺',), '.ZushiHayama': ('逗子・葉山',),
}

PDF_TO_ODPT_SUFFIX = {
    "泉岳寺": "Sengakuji",
    "三田": "Mita",
    "大門": "Daimon",
    "新橋": "Shimbashi",
    "東銀座": "HigashiGinza",
    "宝町": "Takaracho",
    "日本橋": "Nihombashi",
    "人形町": "Ningyocho",
    "東日本橋": "HigashiNihombashi",
    "浅草橋": "Asakusabashi",
    "蔵前": "Kuramae",
    "浅草": "Asakusa",
    "本所吾妻橋": "HonjoAzumabashi",
    "押上": "Oshiage",
}

def station_suffix_map() -> dict[str, str]:
    output: dict[str, str] = {}
    duplicate: set[str] = set()
    for suffix, labels in STATION_LABELS.items():
        for label in labels:
            key = norm(label)
            if not key:
                continue
            if key in output and output[key] != suffix:
                duplicate.add(key)
            else:
                output[key] = suffix
    for key in duplicate:
        output.pop(key, None)
    return output

