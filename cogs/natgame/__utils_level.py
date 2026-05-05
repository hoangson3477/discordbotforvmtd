def ensure_nation_level(supabase, nation_id: str):
    res = (
        supabase.table("nation_levels")
        .select("*")
        .eq("nation_id", nation_id)
        .single()
        .execute()
    )

    if not res.data:
        supabase.table("nation_levels").insert({
            "nation_id": nation_id,
            "level": 1,
            "exp": 0
        }).execute()

        return {"level": 1, "exp": 0}

    return res.data

def add_nation_exp(supabase, nation_id: str, amount: int):
    data = (
        supabase.table("nation_levels")
        .select("level, exp")
        .eq("nation_id", nation_id)
        .single()
        .execute()
        .data
    )

    level = data["level"]
    exp = data["exp"] + amount

    leveled_up = False

    while exp >= level * 100:
        exp -= level * 100
        level += 1
        leveled_up = True

    supabase.table("nation_levels").update({
        "level": level,
        "exp": exp
    }).eq("nation_id", nation_id).execute()

    return leveled_up, level
