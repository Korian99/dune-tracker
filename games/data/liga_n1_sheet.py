"""
Historical games from Google Sheets for Liga N°1 (May 2026).

Imported via management command or migration 0005; idempotent by import_key.
"""

from datetime import date

# Each game: played_on, rounds, duration_minutes, import_key, results[]
# Result: player, leader, victory_points, alliances dict, sardaukar_count

LIGA_N1_GAMES = [
    {
        "import_key": "liga-n1-2026-05-16-a",
        "played_on": date(2026, 5, 16),
        "rounds": 6,
        "duration_minutes": 85,
        "results": [
            {
                "player": "Roger",
                "leader": "Steersman Y'Rkoon",
                "victory_points": 10,
                "sardaukar_count": 1,
            },
            {
                "player": "Kori",
                "leader": "Princess Irulan",
                "victory_points": 7,
                "sardaukar_count": 1,
            },
            {
                "player": "Pitufo",
                "leader": "Lady Amber Metulli",
                "victory_points": 6,
                "sardaukar_count": 3,
            },
            {
                "player": "Nano",
                "leader": "Shadam Corrino IV",
                "victory_points": 3,
                "sardaukar_count": 0,
            },
        ],
    },
    {
        "import_key": "liga-n1-2026-05-16-b",
        "played_on": date(2026, 5, 16),
        "rounds": 8,
        "duration_minutes": 125,
        "results": [
            {
                "player": "Anita",
                "leader": "Esmar Tuek",
                "victory_points": 12,
                "alliance_guild": True,
                "alliance_fremen": True,
            },
            {
                "player": "Roger",
                "leader": "Lady Margot Fenring",
                "victory_points": 10,
                "alliance_fremen": True,
                "sardaukar_count": 2,
            },
            {
                "player": "Pitufo",
                "leader": "Duncan Idaho",
                "victory_points": 9,
                "alliance_bene_gesserit": True,
            },
            {
                "player": "Nano",
                "leader": "Staban Tuek",
                "victory_points": 6,
            },
        ],
    },
    {
        "import_key": "liga-n1-2026-05-17-a",
        "played_on": date(2026, 5, 17),
        "rounds": 7,
        "duration_minutes": 132,
        "results": [
            {
                "player": "Matías",
                "leader": "Liet Kynes",
                "victory_points": 11,
                "alliance_emperor": True,
            },
            {
                "player": "Pitufo",
                "leader": "Kota Odax of Ix",
                "victory_points": 10,
            },
            {
                "player": "Anita",
                "leader": "Shadam Corrino IV",
                "victory_points": 9,
                "alliance_fremen": True,
                "sardaukar_count": 5,
            },
            {
                "player": "Nano",
                "leader": "Lady Jessica",
                "victory_points": 7,
            },
        ],
    },
    {
        "import_key": "liga-n1-2026-05-17-b",
        "played_on": date(2026, 5, 17),
        "rounds": 7,
        "duration_minutes": 83,
        "results": [
            {
                "player": "Anita",
                "leader": "Princess Irulan",
                "victory_points": 11,
                "alliance_fremen": True,
            },
            {
                "player": "Matías",
                "leader": "Staban Tuek",
                "victory_points": 11,
                "sardaukar_count": 3,
            },
            {
                "player": "Pitufo",
                "leader": "Piter de Vries",
                "victory_points": 7,
                "sardaukar_count": 1,
            },
            {
                "player": "Nano",
                "leader": "Muad'Dib",
                "victory_points": 6,
                "alliance_bene_gesserit": True,
                "alliance_fremen": True,
            },
        ],
    },
    {
        "import_key": "liga-n1-2026-05-22-a",
        "played_on": date(2026, 5, 22),
        "rounds": 8,
        "duration_minutes": 150,
        "results": [
            {
                "player": "Anita",
                "leader": "Princess Irulan",
                "victory_points": 14,
                "alliance_emperor": True,
                "alliance_fremen": True,
                "sardaukar_count": 2,
            },
            {
                "player": "Pitufo",
                "leader": "Duncan Idaho",
                "victory_points": 10,
                "alliance_fremen": True,
            },
            {
                "player": "Nano",
                "leader": "Staban Tuek",
                "victory_points": 8,
            },
            {
                "player": "Matías",
                "leader": "Liet Kynes",
                "victory_points": 7,
                "sardaukar_count": 2,
            },
        ],
    },
    {
        "import_key": "liga-n1-2026-05-22-b",
        "played_on": date(2026, 5, 22),
        "rounds": 8,
        "duration_minutes": 102,
        "results": [
            {
                "player": "Nano",
                "leader": "Gurney Halleck",
                "victory_points": 11,
                "alliance_fremen": True,
                "sardaukar_count": 1,
            },
            {
                "player": "Kori",
                "leader": "Gaius Helen Mohiam",
                "victory_points": 10,
            },
            {
                "player": "Matías",
                "leader": "Esmar Tuek",
                "victory_points": 7,
                "alliance_bene_gesserit": True,
                "sardaukar_count": 1,
            },
            {
                "player": "Pitufo",
                "leader": "Chani",
                "victory_points": 5,
                "sardaukar_count": 1,
            },
        ],
    },
    {
        "import_key": "liga-n1-2026-05-25-a",
        "played_on": date(2026, 5, 25),
        "rounds": 8,
        "duration_minutes": 134,
        "results": [
            {
                "player": "Anita",
                "leader": "Staban Tuek",
                "victory_points": 12,
                "alliance_fremen": True,
            },
            {
                "player": "Matías",
                "leader": "Liet Kynes",
                "victory_points": 9,
                "alliance_emperor": True,
                "sardaukar_count": 4,
            },
            {
                "player": "Roger",
                "leader": "Lady Jessica",
                "victory_points": 8,
            },
            {
                "player": "Nano",
                "leader": "Gurney Halleck",
                "victory_points": 8,
                "sardaukar_count": 1,
            },
        ],
    },
    {
        "import_key": "liga-n1-2026-05-25-b",
        "played_on": date(2026, 5, 25),
        "rounds": 7,
        "duration_minutes": 90,
        "results": [
            {
                "player": "Roger",
                "leader": "Steersman Y'Rkoon",
                "victory_points": 11,
            },
            {
                "player": "Anita",
                "leader": "Feyd-Rautha Harkonnen",
                "victory_points": 10,
            },
            {
                "player": "Matías",
                "leader": "Chani",
                "victory_points": 7,
            },
            {
                "player": "Nano",
                "leader": "Shadam Corrino IV",
                "victory_points": 7,
            },
        ],
    },
    {
        "import_key": "liga-n1-2026-05-29",
        "played_on": date(2026, 5, 29),
        "rounds": 6,
        "duration_minutes": 114,
        "results": [
            {
                "player": "Anita",
                "leader": "Steersman Y'Rkoon",
                "victory_points": 12,
                "alliance_guild": True,
                "alliance_fremen": True,
                "sardaukar_count": 1,
            },
            {
                "player": "Matías",
                "leader": "Staban Tuek",
                "victory_points": 7,
                "alliance_emperor": True,
                "sardaukar_count": 3,
            },
            {
                "player": "Pitufo",
                "leader": "Kota Odax of Ix",
                "victory_points": 7,
                "sardaukar_count": 1,
            },
            {
                "player": "Nano",
                "leader": "Gurney Halleck",
                "victory_points": 4,
            },
        ],
    },
    {
        "import_key": "liga-n1-2026-05-30-a",
        "played_on": date(2026, 5, 30),
        "rounds": 8,
        "duration_minutes": 106,
        "results": [
            {
                "player": "Kori",
                "leader": "Staban Tuek",
                "victory_points": 11,
                "alliance_fremen": True,
                "sardaukar_count": 2,
            },
            {
                "player": "Roger",
                "leader": "Chani",
                "victory_points": 10,
                "alliance_emperor": True,
                "alliance_fremen": True,
                "sardaukar_count": 2,
            },
            {
                "player": "Nano",
                "leader": "Liet Kynes",
                "victory_points": 10,
                "alliance_fremen": True,
                "sardaukar_count": 1,
            },
            {
                "player": "Pitufo",
                "leader": "Feyd-Rautha Harkonnen",
                "victory_points": 8,
                "alliance_bene_gesserit": True,
                "sardaukar_count": 2,
            },
        ],
    },
    {
        "import_key": "liga-n1-2026-05-30-b",
        "played_on": date(2026, 5, 30),
        "rounds": 7,
        "duration_minutes": 80,
        "results": [
            {
                "player": "Kori",
                "leader": "Steersman Y'Rkoon",
                "victory_points": 10,
                "alliance_emperor": True,
                "sardaukar_count": 1,
            },
            {
                "player": "Roger",
                "leader": "Count Hasimir Fenring",
                "victory_points": 10,
                "alliance_emperor": True,
                "alliance_fremen": True,
                "sardaukar_count": 1,
            },
            {
                "player": "Pitufo",
                "leader": "Gurney Halleck",
                "victory_points": 8,
                "sardaukar_count": 1,
            },
            {
                "player": "Nano",
                "leader": "Muad'Dib",
                "victory_points": 5,
                "alliance_bene_gesserit": True,
            },
        ],
    },
]
