-- ============================================
-- NATGAME DATABASE UPDATE
-- Bổ sung tables cho features mới
-- Chạy sau khi đã chạy database_schema.sql
-- ============================================

-- ============================================
-- 11. NATION UPGRADES TABLE (cho shop)
-- ============================================
CREATE TABLE IF NOT EXISTS nation_upgrades (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    nation_id UUID NOT NULL REFERENCES nations(id) ON DELETE CASCADE,
    upgrade_type TEXT NOT NULL,  -- pop_growth, exp_boost, defense_boost
    quantity INTEGER DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(nation_id, upgrade_type)
);

CREATE INDEX idx_nation_upgrades_nation ON nation_upgrades(nation_id);

-- ============================================
-- 12. QUEST PROGRESS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS quest_progress (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    nation_id UUID NOT NULL REFERENCES nations(id) ON DELETE CASCADE,
    quest_id TEXT NOT NULL,
    progress INTEGER DEFAULT 0,
    completed BOOLEAN DEFAULT FALSE,
    claimed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(nation_id, quest_id)
);

CREATE INDEX idx_quest_progress_nation ON quest_progress(nation_id);
CREATE INDEX idx_quest_progress_completed ON quest_progress(completed);

-- ============================================
-- 13. ACHIEVEMENTS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS achievements (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    nation_id UUID NOT NULL REFERENCES nations(id) ON DELETE CASCADE,
    achievement_id TEXT NOT NULL,
    achieved_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(nation_id, achievement_id)
);

CREATE INDEX idx_achievements_nation ON achievements(nation_id);

-- ============================================
-- 14. WAR PROTECTION TABLE (cho war cooldown)
-- ============================================
CREATE TABLE IF NOT EXISTS war_protection (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    nation_id UUID NOT NULL REFERENCES nations(id) ON DELETE CASCADE,
    protected_until TIMESTAMPTZ NOT NULL,
    reason TEXT,  -- 'lost_war', 'new_nation', etc.
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(nation_id)
);

CREATE INDEX idx_war_protection_until ON war_protection(protected_until);

-- ============================================
-- 15. EVENT LOG TABLE (cho tracking)
-- ============================================
CREATE TABLE IF NOT EXISTS event_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    nation_id UUID REFERENCES nations(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,  -- 'random_event', 'war_win', 'quest_complete', etc.
    event_data JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_event_logs_nation ON event_logs(nation_id);
CREATE INDEX idx_event_logs_type ON event_logs(event_type);

-- ============================================
-- FUNCTIONS UPDATE
-- ============================================

-- Function: Kiểm tra và cấp achievements
CREATE OR REPLACE FUNCTION check_achievements(p_nation_id UUID)
RETURNS TABLE(achievement_id TEXT, newly_granted BOOLEAN) AS $$
DECLARE
    v_army INTEGER;
    v_money INTEGER;
    v_population INTEGER;
    v_level INTEGER;
    v_war_wins INTEGER;
BEGIN
    -- Lấy thông tin nation
    SELECT n.army, n.money, n.population, nl.level
    INTO v_army, v_money, v_population, v_level
    FROM nations n
    LEFT JOIN nation_levels nl ON n.id = nl.nation_id
    WHERE n.id = p_nation_id;

    -- Đếm số war thắng
    SELECT COUNT(*) INTO v_war_wins
    FROM wars WHERE winner_nation_id = p_nation_id;

    -- Rich achievement
    IF v_money >= 10000 THEN
        RETURN QUERY SELECT 'rich'::TEXT, 
            NOT EXISTS(SELECT 1 FROM achievements WHERE nation_id = p_nation_id AND achievement_id = 'rich');
    END IF;

    -- Level achievements
    IF v_level >= 10 THEN
        RETURN QUERY SELECT 'level_10'::TEXT,
            NOT EXISTS(SELECT 1 FROM achievements WHERE nation_id = p_nation_id AND achievement_id = 'level_10');
    ELSIF v_level >= 5 THEN
        RETURN QUERY SELECT 'level_5'::TEXT,
            NOT EXISTS(SELECT 1 FROM achievements WHERE nation_id = p_nation_id AND achievement_id = 'level_5');
    END IF;

    -- Population achievement
    IF v_population >= 1000 THEN
        RETURN QUERY SELECT 'population'::TEXT,
            NOT EXISTS(SELECT 1 FROM achievements WHERE nation_id = p_nation_id AND achievement_id = 'population');
    END IF;

    -- War win achievements
    IF v_war_wins >= 50 THEN
        RETURN QUERY SELECT 'warlord'::TEXT,
            NOT EXISTS(SELECT 1 FROM achievements WHERE nation_id = p_nation_id AND achievement_id = 'warlord');
    ELSIF v_war_wins >= 10 THEN
        RETURN QUERY SELECT 'veteran'::TEXT,
            NOT EXISTS(SELECT 1 FROM achievements WHERE nation_id = p_nation_id AND achievement_id = 'veteran');
    ELSIF v_war_wins >= 1 THEN
        RETURN QUERY SELECT 'first_blood'::TEXT,
            NOT EXISTS(SELECT 1 FROM achievements WHERE nation_id = p_nation_id AND achievement_id = 'first_blood');
    END IF;

    RETURN;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- END OF UPDATE
-- ============================================
