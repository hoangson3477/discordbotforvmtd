from cogs.natgame.__db import supabase
class WarService:
    def __init__(self, adapter):
        self.adapter = adapter

    def resolve_war(self, war_id):
        result = self.adapter.run_war(war_id)
        self.adapter.apply_result(war_id, result)
        return result
