from cogs.natgame.__db import supabase

class CombatEngine:
    def __init__(self, attacker_army, defense_lines, garrison):
        self.attacker_army = attacker_army
        self.defense_lines = defense_lines
        self.garrison = garrison
        self.logs = []
        self.round = 1

    # ======================
    # UTIL
    # ======================
    def total_attackers(self):
        return sum(a["troops"] for a in self.attacker_army)

    def total_defenders(self):
        total = sum(line["troops"] for line in self.defense_lines)
        total += self.garrison["army"]
        total += sum(u["troops"] for u in self.garrison["idle_units"])
        return total

    def reduce_attackers(self, loss):
        for group in self.attacker_army:
            if loss <= 0:
                break
            if group["troops"] <= loss:
                loss -= group["troops"]
                group["troops"] = 0
            else:
                group["troops"] -= loss
                loss = 0

    # ======================
    # DEFENSE PHASE
    # ======================
    def fight_defense_lines(self):
        for line in self.defense_lines:
            if self.total_attackers() <= 0:
                return False

            atk = self.total_attackers()
            defn = line["troops"]

            # Attacker thiệt hại 30-50% quân defender (random)
            # Defender thiệt hại 50-70% quân attacker (vì phòng thủ có lợi thế)
            import random
            atk_loss_ratio = random.uniform(0.50, 0.70)  # Attacker chịu thiệt hại nặng hơn
            def_loss_ratio = random.uniform(0.30, 0.50)  # Defender chịu ít hơn

            atk_loss = min(atk, int(defn * atk_loss_ratio))
            def_loss = min(defn, int(atk * def_loss_ratio))

            # Đảm bảo có thiệt hại tối thiểu
            if atk_loss == 0 and defn > 0:
                atk_loss = min(atk, max(1, int(defn * 0.3)))
            if def_loss == 0 and atk > 0:
                def_loss = min(defn, max(1, int(atk * 0.3)))

            self.reduce_attackers(atk_loss)
            line["troops"] -= def_loss

            self.logs.append({
                "round": self.round,
                "phase": "defense",
                "attacker_loss": atk_loss,
                "defender_loss": def_loss,
                "description": f"Đánh tuyến phòng thủ slot {line['slot']}: Attacker -{atk_loss}, Defender -{def_loss}"
            })

            self.round += 1

            if line["troops"] > 0:
                return False

        return True

    # ======================
    # CITY PHASE
    # ======================
    def fight_city(self):
        import random

        city_troops = self.garrison["army"]
        for u in self.garrison["idle_units"]:
            city_troops += u["troops"]

        atk = self.total_attackers()

        # Trong city fight, quân thủ thành (garrison) chịu thiệt hại nặng hơn
        # vì không có công sự phòng thủ
        atk_loss_ratio = random.uniform(0.40, 0.60)  # Attacker bị thiệt hại vừa
        def_loss_ratio = random.uniform(0.60, 0.80)  # Defender garrison bị nặng

        atk_loss = min(atk, int(city_troops * atk_loss_ratio))
        def_loss = min(city_troops, int(atk * def_loss_ratio))

        # Đảm bảo thiệt hại tối thiểu
        if atk_loss == 0 and city_troops > 0:
            atk_loss = min(atk, max(1, int(city_troops * 0.4)))
        if def_loss == 0 and atk > 0:
            def_loss = min(city_troops, max(1, int(atk * 0.4)))

        self.reduce_attackers(atk_loss)
        city_troops -= def_loss

        # Update garrison
        self.garrison["army"] = max(0, city_troops - sum(u["troops"] for u in self.garrison["idle_units"]))

        self.logs.append({
            "round": self.round,
            "phase": "city",
            "attacker_loss": atk_loss,
            "defender_loss": def_loss,
            "description": f"Tấn công thành: Attacker -{atk_loss}, Garrison -{def_loss}"
        })

        self.round += 1

        return atk > city_troops

    # ======================
    # RUN
    # ======================
    def run(self):
        if not self.fight_defense_lines():
            return self._build_result("defender_win")

        if self.fight_city():
            return self._build_result("attacker_win")

        return self._build_result("defender_win")

    def _build_result(self, result):
        return {
            "result": result,
            "logs": self.logs,
            "attacker_remaining": self.total_attackers(),
            "defender_remaining": self.total_defenders()
        }