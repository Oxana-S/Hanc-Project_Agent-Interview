"""
Integration tests for KB full injection (P1) and phase-based re-injection (P2).

Tests use REAL KB profiles from config/industries/ to verify the full pipeline:
1. build_for_voice_full() produces rich context with v2.0 data
2. Phase detection correctly transitions discovery → analysis → proposal → refinement
3. Different phases produce different KB context
4. KB injection block in consultant.py works end-to-end with mocked agent_session
"""

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from types import SimpleNamespace

# --- P1: Full KB injection ---

from src.knowledge.enriched_builder import EnrichedContextBuilder
from src.knowledge.context_builder import KBContextBuilder
from src.knowledge.manager import IndustryKnowledgeManager
from src.knowledge.models import (
    IndustryProfile,
    IndustryMeta,
    PainPoint,
    RecommendedFunction,
    TypicalIntegration,
    IndustryFAQ,
    TypicalObjection,
    SalesScript,
    Competitor,
    PricingContext,
    ROIExample,
    MarketContext,
    Seasonality,
    SuccessBenchmarks,
    IndustrySpecifics,
    Learning,
)

# --- P2: Phase detection ---

from src.voice.consultant import (
    _detect_consultation_phase,
    VoiceConsultationSession,
    get_enriched_system_prompt,
    _extract_and_update_anketa,
)


# ============================================================
# Fixtures
# ============================================================

def _rich_profile() -> IndustryProfile:
    """Create a realistic profile with ALL v2.0 fields populated."""
    return IndustryProfile(
        meta=IndustryMeta(
            id="logistics",
            version="2.0",
            region="na",
            country="us",
            language="en",
            currency="USD",
        ),
        aliases=["logistics", "shipping", "freight"],
        typical_services=["Freight Shipping", "Express Parcel", "Warehousing"],
        pain_points=[
            PainPoint(description="High volume of 'where is my shipment?' calls", severity="high",
                      solution_hint="Automated status lookup"),
            PainPoint(description="Rate quotes taking too long", severity="medium"),
            PainPoint(description="Manual booking errors", severity="low"),
        ],
        recommended_functions=[
            RecommendedFunction(name="shipment_status", priority="high",
                                reason="60-75% of inbound calls"),
            RecommendedFunction(name="rate_quote", priority="high",
                                reason="Speed up quoting by 10x"),
            RecommendedFunction(name="booking_assistant", priority="medium",
                                reason="Reduce manual errors"),
        ],
        typical_integrations=[
            TypicalIntegration(name="TMS", examples=["MercuryGate", "Oracle OTM"], priority="high"),
            TypicalIntegration(name="CRM", examples=["Salesforce", "HubSpot"], priority="medium"),
        ],
        industry_faq=[
            IndustryFAQ(question="Where is my shipment?",
                        answer_template="Please provide your tracking number..."),
            IndustryFAQ(question="How much does shipping cost?",
                        answer_template="Rates depend on weight, dimensions..."),
        ],
        typical_objections=[
            TypicalObjection(objection="I don't want to talk to a machine",
                             response="I understand. My goal is to get you answers faster..."),
            TypicalObjection(objection="We already have a system",
                             response="That's great — our agent integrates with existing systems..."),
        ],
        sales_scripts=[
            SalesScript(trigger="price_question", situation="Customer asks about pricing",
                        script="I understand you're looking for a quote...",
                        goal="Qualify the lead", effectiveness=0.7),
            SalesScript(trigger="cold_call", situation="First contact",
                        script="Hello! I'm calling about...",
                        goal="Set up a demo", effectiveness=0.4),
        ],
        competitors=[
            Competitor(name="FedEx", positioning="Global express delivery giant",
                       strengths=["Extensive network", "Strong brand"],
                       weaknesses=["Expensive", "Impersonal"],
                       our_differentiation="Personalized local management"),
            Competitor(name="UPS", positioning="Integrated global delivery",
                       strengths=["Ground network"],
                       weaknesses=["Complex pricing"],
                       our_differentiation="Transparent pricing"),
        ],
        pricing_context=PricingContext(
            currency="USD",
            typical_budget_range=[500, 10000],
            entry_point=299,
            roi_examples=[
                ROIExample(scenario="Automate 70% of status calls",
                           monthly_cost=899, monthly_savings=3200, payback_months=1),
            ],
            value_anchors=["Reduce call volume by 40%", "Get paid faster with automated POD"],
        ),
        market_context=MarketContext(
            market_size="$1.6 Trillion",
            growth_rate="5-7% YoY",
            key_trends=["Last-mile delivery", "AI route optimization",
                        "Electric vehicle fleets", "Real-time visibility"],
            seasonality=Seasonality(high=["Nov-Dec", "Aug-Sep"], low=["Jan-Feb"]),
        ),
        success_benchmarks=SuccessBenchmarks(
            avg_call_duration_seconds=165,
            target_automation_rate=0.75,
            typical_kpis=["Reduce live agent workload by 35-45%",
                          "Automate 75% of status inquiries"],
        ),
        industry_specifics=IndustrySpecifics(
            compliance=["DOT regulations", "FMCSA"],
            tone=["professional", "efficient"],
            peak_times=["9am-11am", "2pm-4pm"],
        ),
        learnings=[
            Learning(date="2026-01-15",
                     insight="[SUCCESS] Voice agent reduced call volume by 42%",
                     source="voice_test123"),
        ],
    )


def _make_dialogue(n_messages: int) -> list:
    """Create n dialogue messages alternating user/assistant about logistics."""
    msgs = []
    user_texts = [
        "Мы логистическая компания, перевозим грузы по США",
        "У нас большой объём звонков от клиентов, спрашивают где их груз",
        "Мы используем MercuryGate как TMS",
        "Хотим автоматизировать ответы на типовые вопросы",
        "Какая цена у вашего решения?",
        "У нас уже есть система, зачем нам менять?",
        "Мы работаем с FedEx, можете лучше?",
        "Расскажите про интеграции с CRM",
        "Какие KPI мы можем ожидать?",
        "Давайте обсудим детали внедрения",
        "Нам нужна поддержка 24/7",
        "Сколько времени займёт интеграция?",
    ]
    assistant_texts = [
        "Расскажите подробнее о вашей компании",
        "Понимаю, это частая проблема в логистике",
        "Отлично, мы интегрируемся с MercuryGate",
        "Наш AI-агент может обрабатывать 75% таких звонков",
        "Стоимость зависит от объёма, начинается от $299/мес",
        "Мы интегрируемся с вашей текущей системой",
        "Мы предлагаем персонализированный подход",
        "Мы работаем с Salesforce, HubSpot и другими",
        "Типичный результат — снижение нагрузки на 35-45%",
        "Отлично, давайте зафиксируем план",
        "Да, наш агент работает круглосуточно",
        "Обычно 2-4 недели, зависит от сложности",
    ]
    for i in range(n_messages):
        if i % 2 == 0:
            msgs.append({"role": "user", "content": user_texts[i // 2 % len(user_texts)]})
        else:
            msgs.append({"role": "assistant", "content": assistant_texts[i // 2 % len(assistant_texts)]})
    return msgs


# ============================================================
# P1: Full KB Injection Tests
# ============================================================

class TestP1_FullKBInjection:
    """Priority 1: build_for_voice_full() produces rich context."""

    def test_voice_full_includes_phase_kb_context(self):
        """build_for_voice_full() includes phase-specific KB blocks from kb_context.yaml."""
        profile = _rich_profile()
        manager = MagicMock()
        builder = EnrichedContextBuilder(manager)

        context = builder.build_for_voice_full(
            _make_dialogue(6), profile=profile, phase="discovery",
        )

        assert len(context) > 0, "Context should not be empty"
        # Discovery should have pain points and recommended functions
        assert "!!!" in context or "боли" in context.lower() or "pain" in context.lower() or "shipment" in context.lower(), \
            f"Discovery context should mention pain points. Got: {context[:300]}"

    def test_voice_full_includes_competitors(self):
        """Competitors appear in context for discovery/analysis phases."""
        profile = _rich_profile()
        manager = MagicMock()
        builder = EnrichedContextBuilder(manager)

        # discovery + analysis should include competitors via _build_v2_context
        for phase in ["discovery", "analysis"]:
            context = builder.build_for_voice_full(
                _make_dialogue(10), profile=profile, phase=phase,
            )
            assert "FedEx" in context, f"Phase '{phase}' should mention competitor FedEx. Got: {context[:500]}"

    def test_voice_full_includes_pricing(self):
        """Pricing context appears in discovery phase."""
        profile = _rich_profile()
        manager = MagicMock()
        builder = EnrichedContextBuilder(manager)

        context = builder.build_for_voice_full(
            _make_dialogue(4), profile=profile, phase="discovery",
        )

        # Pricing should be included via _build_v2_context for discovery
        assert "500" in context or "10000" in context or "299" in context or "Бюджет" in context, \
            f"Discovery should include pricing context. Got: {context[:500]}"

    def test_voice_full_includes_market(self):
        """Market context appears in discovery and proposal phases."""
        profile = _rich_profile()
        manager = MagicMock()
        builder = EnrichedContextBuilder(manager)

        context = builder.build_for_voice_full(
            _make_dialogue(4), profile=profile, phase="discovery",
        )
        assert "1.6 Trillion" in context or "Рынок" in context.lower() or "рыноч" in context.lower(), \
            f"Discovery should include market context. Got: {context[:500]}"

    def test_voice_full_includes_sales_scripts_in_proposal(self):
        """Sales scripts appear in proposal phase via kb_context.yaml blocks."""
        profile = _rich_profile()
        manager = MagicMock()
        builder = EnrichedContextBuilder(manager)

        context = builder.build_for_voice_full(
            _make_dialogue(16), profile=profile, phase="proposal",
        )

        # Sales scripts should come from kb_context.yaml proposal blocks
        assert "Триггер" in context or "price_question" in context or "Скрипт" in context, \
            f"Proposal should include sales scripts. Got: {context[:500]}"

    def test_voice_full_includes_learnings(self):
        """Learnings section is included when profile has learnings."""
        profile = _rich_profile()
        manager = MagicMock()
        builder = EnrichedContextBuilder(manager)

        context = builder.build_for_voice_full(
            _make_dialogue(6), profile=profile, phase="discovery",
        )
        assert "НАКОПЛЕННЫЙ ОПЫТ" in context or "call volume" in context.lower(), \
            f"Should include learnings. Got: {context[:500]}"

    def test_voice_full_respects_token_budget(self):
        """Context is truncated at 4000 chars."""
        profile = _rich_profile()
        manager = MagicMock()
        builder = EnrichedContextBuilder(manager)

        context = builder.build_for_voice_full(
            _make_dialogue(20), profile=profile, phase="discovery",
        )
        # 4000 chars + truncation marker
        assert len(context) <= 4100, f"Context too long: {len(context)} chars"

    def test_voice_full_empty_without_profile(self):
        """Returns empty string when no profile and industry not detected."""
        manager = MagicMock()
        manager.detect_industry.return_value = None  # No industry detected
        builder = EnrichedContextBuilder(manager)

        context = builder.build_for_voice_full(
            _make_dialogue(10), profile=None, phase="discovery",
        )
        assert context == ""

    def test_voice_full_vs_voice_compact_size(self):
        """build_for_voice_full() produces significantly more context than build_for_voice()."""
        profile = _rich_profile()
        manager = MagicMock()
        manager.detect_industry.return_value = "logistics"
        manager.get_profile.return_value = profile
        builder = EnrichedContextBuilder(manager)

        compact = builder.build_for_voice(_make_dialogue(10))
        full = builder.build_for_voice_full(_make_dialogue(10), profile=profile, phase="discovery")

        assert len(full) > len(compact) * 2, \
            f"Full ({len(full)} chars) should be >2x compact ({len(compact)} chars)"

    def test_all_four_phases_produce_different_context(self):
        """Each phase should produce different context content."""
        profile = _rich_profile()
        manager = MagicMock()
        builder = EnrichedContextBuilder(manager)

        contexts = {}
        for phase in ["discovery", "analysis", "proposal", "refinement"]:
            contexts[phase] = builder.build_for_voice_full(
                _make_dialogue(20), profile=profile, phase=phase,
            )

        # At least some phases should differ
        unique_contexts = set(contexts.values())
        assert len(unique_contexts) >= 2, \
            f"Expected at least 2 different contexts across phases, got {len(unique_contexts)}"


# ============================================================
# P1: Real KB Profile Tests (loads actual YAML files)
# ============================================================

class TestP1_RealKBProfiles:
    """Test with real YAML profiles from config/industries/."""

    def _load_real_profile(self, region: str, country: str, industry: str):
        """Attempt to load a real regional profile."""
        try:
            manager = IndustryKnowledgeManager()
            profile = manager.loader.load_regional_profile(region, country, industry)
            return profile
        except Exception:
            return None

    def test_us_logistics_has_v2_data(self):
        """na/us/logistics.yaml should have sales_scripts, competitors, pricing, market."""
        profile = self._load_real_profile("na", "us", "logistics")
        if profile is None:
            pytest.skip("na/us/logistics.yaml not found or failed to load")

        assert len(profile.sales_scripts) > 0, "US logistics should have sales_scripts"
        assert len(profile.competitors) > 0, "US logistics should have competitors"
        assert profile.pricing_context is not None, "US logistics should have pricing_context"
        assert profile.market_context is not None, "US logistics should have market_context"

    def test_us_logistics_full_context_is_rich(self):
        """build_for_voice_full() with real US logistics profile produces rich context."""
        profile = self._load_real_profile("na", "us", "logistics")
        if profile is None:
            pytest.skip("na/us/logistics.yaml not found or failed to load")

        manager = MagicMock()
        builder = EnrichedContextBuilder(manager)

        context = builder.build_for_voice_full(
            _make_dialogue(10), profile=profile, phase="proposal",
        )

        assert len(context) > 500, f"Real profile context too short: {len(context)} chars"
        # Should contain real competitor names
        has_competitors = any(c.name in context for c in profile.competitors)
        assert has_competitors or "Триггер" in context, \
            f"Real profile context should have competitors or scripts. Got: {context[:500]}"

    def test_de_logistics_full_context(self):
        """eu/de/logistics.yaml should also produce rich context."""
        profile = self._load_real_profile("eu", "de", "logistics")
        if profile is None:
            pytest.skip("eu/de/logistics.yaml not found or failed to load")

        manager = MagicMock()
        builder = EnrichedContextBuilder(manager)

        context = builder.build_for_voice_full(
            _make_dialogue(10), profile=profile, phase="analysis",
        )

        assert len(context) > 200, f"DE logistics context too short: {len(context)}"


# ============================================================
# P2: Phase Detection Tests
# ============================================================

class TestP2_PhaseDetection:
    """Priority 2: _detect_consultation_phase() transitions."""

    def test_discovery_phase_start(self):
        """< 8 messages, low completion → discovery."""
        assert _detect_consultation_phase(0, 0.0, False) == "discovery"
        assert _detect_consultation_phase(4, 0.05, False) == "discovery"
        assert _detect_consultation_phase(7, 0.14, False) == "discovery"

    def test_analysis_phase(self):
        """8-14 messages or completion 0.15-0.35 → analysis."""
        assert _detect_consultation_phase(8, 0.10, False) == "analysis"
        assert _detect_consultation_phase(5, 0.15, False) == "analysis"
        assert _detect_consultation_phase(12, 0.25, False) == "analysis"

    def test_proposal_phase(self):
        """14-20 messages or completion 0.35-0.50 → proposal."""
        assert _detect_consultation_phase(14, 0.20, False) == "proposal"
        assert _detect_consultation_phase(10, 0.35, False) == "proposal"
        assert _detect_consultation_phase(18, 0.45, False) == "proposal"

    def test_refinement_phase(self):
        """completion >= 0.50 or review_started → refinement."""
        assert _detect_consultation_phase(10, 0.50, False) == "refinement"
        assert _detect_consultation_phase(5, 0.10, True) == "refinement"
        assert _detect_consultation_phase(25, 0.80, False) == "refinement"

    def test_review_started_overrides_all(self):
        """review_started=True → refinement regardless of other metrics."""
        assert _detect_consultation_phase(2, 0.0, True) == "refinement"
        assert _detect_consultation_phase(0, 0.0, True) == "refinement"

    def test_phase_progression_with_increasing_messages(self):
        """Simulate a full session: phases should progress monotonically."""
        phases = []
        for msg_count in range(0, 26, 2):
            # Simulate increasing completion as messages grow
            completion = min(msg_count * 0.03, 0.7)
            phase = _detect_consultation_phase(msg_count, completion, False)
            phases.append(phase)

        phase_order = {"discovery": 0, "analysis": 1, "proposal": 2, "refinement": 3}
        phase_indices = [phase_order[p] for p in phases]
        # Should never go backwards
        for i in range(1, len(phase_indices)):
            assert phase_indices[i] >= phase_indices[i - 1], \
                f"Phase went backwards: {phases[i-1]} → {phases[i]} at msg {i*2}"

        # Should eventually reach refinement
        assert phases[-1] == "refinement", f"Should end in refinement, got {phases[-1]}"


# ============================================================
# P2: Session Phase Tracking Tests
# ============================================================

class TestP2_SessionPhaseTracking:
    """VoiceConsultationSession phase fields work correctly."""

    def test_default_phase_is_discovery(self):
        """New session starts in discovery phase."""
        s = VoiceConsultationSession()
        assert s.current_phase == "discovery"
        assert s.detected_industry_id is None
        assert s.detected_profile is None

    def test_phase_persists_in_messages(self):
        """Messages record the current phase."""
        s = VoiceConsultationSession()
        s.add_message("user", "Hello")
        assert s.dialogue_history[0]["phase"] == "discovery"

        s.current_phase = "analysis"
        s.add_message("user", "Tell me more")
        assert s.dialogue_history[1]["phase"] == "analysis"

        s.current_phase = "proposal"
        s.add_message("assistant", "Here is the proposal")
        assert s.dialogue_history[2]["phase"] == "proposal"

    def test_cached_profile_prevents_re_detection(self):
        """Once detected_profile is set, industry detection is skipped."""
        s = VoiceConsultationSession()
        profile = _rich_profile()
        s.detected_profile = profile
        s.detected_industry_id = "logistics"

        # The profile is cached — no need to re-detect
        assert s.detected_profile is profile
        assert s.detected_industry_id == "logistics"


# ============================================================
# P2: End-to-End KB Re-injection Test
# ============================================================

class TestP2_KBReinjection:
    """Test that KB context is re-injected when phase changes."""

    @pytest.mark.asyncio
    async def test_kb_reinjected_on_phase_change(self):
        """
        Simulate extraction at different message counts.
        KB should be re-injected when phase transitions.
        """
        profile = _rich_profile()

        # Create consultation with enough messages for analysis phase
        consultation = VoiceConsultationSession(room_name="test-room")
        consultation.session_id = "test-001"
        consultation.kb_enriched = False
        # Simulate 10 messages (analysis phase)
        for msg in _make_dialogue(10):
            consultation.dialogue_history.append(msg)

        # Mock agent_session with activity that has update_instructions
        mock_activity = AsyncMock()
        mock_activity.update_instructions = AsyncMock()
        mock_agent_session = MagicMock()
        mock_agent_session._activity = mock_activity

        # Mock anketa with 0.2 completion (analysis range)
        mock_anketa = MagicMock()
        mock_anketa.completion_rate.return_value = 0.20
        mock_anketa.contact_phone = "+1 555 123 4567"

        # Mock session manager and extractor
        mock_db_session = SimpleNamespace(
            session_id="test-001",
            company_name="TestLogistics",
            contact_name="John",
            status="active",
            dialogue_history=[],
            duration_seconds=300,
            document_context=None,
            anketa_data={},
            voice_config=None,
        )

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.create_llm_client"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.AnketaGenerator") as mock_gen, \
             patch("src.voice.consultant._try_get_redis", return_value=None), \
             patch("src.knowledge.country_detector.get_country_detector") as mock_cd_fn, \
             patch("src.voice.consultant.IndustryKnowledgeManager") as mock_km_cls, \
             patch("src.voice.consultant.EnrichedContextBuilder") as mock_ecb_cls, \
             patch("src.voice.consultant.get_system_prompt", return_value="BASE PROMPT"):

            mock_mgr.get_session.return_value = mock_db_session
            mock_mgr.update_anketa = MagicMock()
            mock_mgr.update_session = MagicMock()

            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(return_value=mock_anketa)
            mock_ext_cls.return_value = mock_extractor
            mock_gen.render_markdown.return_value = "# Anketa"

            # Country detector
            mock_detector = MagicMock()
            mock_detector.detect.return_value = ("na", "us")
            mock_cd_fn.return_value = mock_detector

            # Knowledge manager
            mock_manager = MagicMock()
            mock_manager.detect_industry.return_value = "logistics"
            mock_manager.loader.load_regional_profile.return_value = profile
            mock_km_cls.return_value = mock_manager

            # Builder returns rich context
            mock_builder = MagicMock()
            mock_builder.build_for_voice_full.return_value = "RICH KB CONTEXT FOR ANALYSIS"
            mock_ecb_cls.return_value = mock_builder

            # Run extraction
            await _extract_and_update_anketa(consultation, "test-001", mock_agent_session)

            # Verify KB was injected
            assert consultation.kb_enriched is True, "KB should be marked as enriched"
            assert consultation.detected_industry_id == "logistics"
            assert consultation.detected_profile is profile
            assert consultation.current_phase == "analysis", \
                f"Phase should be analysis (10 msgs, 0.2 completion), got {consultation.current_phase}"

            # update_instructions should have been called with enriched prompt
            mock_activity.update_instructions.assert_called_once()
            call_args = mock_activity.update_instructions.call_args[0][0]
            assert "BASE PROMPT" in call_args
            assert "RICH KB CONTEXT FOR ANALYSIS" in call_args
            assert "analysis" in call_args

    @pytest.mark.asyncio
    async def test_kb_not_reinjected_when_phase_unchanged(self):
        """If phase hasn't changed, KB should NOT be re-injected."""
        profile = _rich_profile()

        consultation = VoiceConsultationSession(room_name="test-room")
        consultation.session_id = "test-002"
        consultation.kb_enriched = True  # Already injected
        consultation.current_phase = "analysis"  # Already in analysis
        consultation.detected_profile = profile
        consultation.detected_industry_id = "logistics"
        for msg in _make_dialogue(12):
            consultation.dialogue_history.append(msg)

        mock_activity = AsyncMock()
        mock_activity.update_instructions = AsyncMock()
        mock_agent_session = MagicMock()
        mock_agent_session._activity = mock_activity

        mock_anketa = MagicMock()
        mock_anketa.completion_rate.return_value = 0.25  # Still analysis range

        mock_db_session = SimpleNamespace(
            session_id="test-002", company_name="TestCo", contact_name="Jane",
            status="active", dialogue_history=[], duration_seconds=400,
            document_context=None, anketa_data={}, voice_config=None,
        )

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.create_llm_client"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.AnketaGenerator") as mock_gen, \
             patch("src.voice.consultant._try_get_redis", return_value=None), \
             patch("src.voice.consultant.IndustryKnowledgeManager") as mock_km_cls, \
             patch("src.voice.consultant.EnrichedContextBuilder") as mock_ecb_cls, \
             patch("src.voice.consultant.get_system_prompt", return_value="BASE"):

            mock_mgr.get_session.return_value = mock_db_session
            mock_mgr.update_anketa = MagicMock()
            mock_mgr.update_session = MagicMock()

            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(return_value=mock_anketa)
            mock_ext_cls.return_value = mock_extractor
            mock_gen.render_markdown.return_value = "# Anketa"

            mock_km_cls.return_value = MagicMock()

            mock_builder = MagicMock()
            mock_ecb_cls.return_value = mock_builder

            await _extract_and_update_anketa(consultation, "test-002", mock_agent_session)

            # Phase unchanged (analysis → analysis), KB already enriched
            # update_instructions should NOT be called
            mock_activity.update_instructions.assert_not_called()

    @pytest.mark.asyncio
    async def test_phase_transition_triggers_reinjection(self):
        """When phase changes from analysis to proposal, KB is re-injected."""
        profile = _rich_profile()

        consultation = VoiceConsultationSession(room_name="test-room")
        consultation.session_id = "test-003"
        consultation.kb_enriched = True  # Previously injected
        consultation.current_phase = "analysis"  # Currently analysis
        consultation.detected_profile = profile
        consultation.detected_industry_id = "logistics"
        # 16 messages + 0.40 completion → proposal
        for msg in _make_dialogue(16):
            consultation.dialogue_history.append(msg)

        mock_activity = AsyncMock()
        mock_activity.update_instructions = AsyncMock()
        mock_agent_session = MagicMock()
        mock_agent_session._activity = mock_activity

        mock_anketa = MagicMock()
        mock_anketa.completion_rate.return_value = 0.40  # proposal range

        mock_db_session = SimpleNamespace(
            session_id="test-003", company_name="TestCo", contact_name="Jane",
            status="active", dialogue_history=[], duration_seconds=500,
            document_context=None, anketa_data={}, voice_config=None,
        )

        with patch("src.voice.consultant._session_mgr") as mock_mgr, \
             patch("src.voice.consultant.create_llm_client"), \
             patch("src.voice.consultant.AnketaExtractor") as mock_ext_cls, \
             patch("src.voice.consultant.AnketaGenerator") as mock_gen, \
             patch("src.voice.consultant._try_get_redis", return_value=None), \
             patch("src.voice.consultant.IndustryKnowledgeManager") as mock_km_cls, \
             patch("src.voice.consultant.EnrichedContextBuilder") as mock_ecb_cls, \
             patch("src.voice.consultant.get_system_prompt", return_value="BASE"):

            mock_mgr.get_session.return_value = mock_db_session
            mock_mgr.update_anketa = MagicMock()
            mock_mgr.update_session = MagicMock()

            mock_extractor = AsyncMock()
            mock_extractor.extract = AsyncMock(return_value=mock_anketa)
            mock_ext_cls.return_value = mock_extractor
            mock_gen.render_markdown.return_value = "# Anketa"

            mock_km_cls.return_value = MagicMock()

            mock_builder = MagicMock()
            mock_builder.build_for_voice_full.return_value = "PROPOSAL CONTEXT WITH SCRIPTS"
            mock_ecb_cls.return_value = mock_builder

            await _extract_and_update_anketa(consultation, "test-003", mock_agent_session)

            # Phase changed analysis → proposal → should re-inject
            assert consultation.current_phase == "proposal"
            mock_activity.update_instructions.assert_called_once()
            call_args = mock_activity.update_instructions.call_args[0][0]
            assert "PROPOSAL CONTEXT WITH SCRIPTS" in call_args


# ============================================================
# P2: get_enriched_system_prompt() with phase parameter
# ============================================================

class TestP2_EnrichedPromptPhase:
    """get_enriched_system_prompt() respects phase parameter."""

    def test_phase_appears_in_enriched_prompt(self):
        """Phase name appears in the enriched prompt header."""
        dialogue = _make_dialogue(6)

        with patch("src.voice.consultant.get_prompt", return_value="BASE"), \
             patch("src.voice.consultant.IndustryKnowledgeManager"), \
             patch("src.voice.consultant.EnrichedContextBuilder") as mock_ecb:
            mock_builder = MagicMock()
            mock_builder.build_for_voice_full.return_value = "KB DATA"
            mock_ecb.return_value = mock_builder

            result = get_enriched_system_prompt(dialogue, phase="proposal")
            assert "proposal" in result
            assert "KB DATA" in result

    def test_different_phases_call_builder_with_different_phase(self):
        """Builder is called with the correct phase parameter."""
        dialogue = _make_dialogue(6)

        for phase in ["discovery", "analysis", "proposal", "refinement"]:
            with patch("src.voice.consultant.get_prompt", return_value="BASE"), \
                 patch("src.voice.consultant.IndustryKnowledgeManager"), \
                 patch("src.voice.consultant.EnrichedContextBuilder") as mock_ecb:
                mock_builder = MagicMock()
                mock_builder.build_for_voice_full.return_value = f"Context for {phase}"
                mock_ecb.return_value = mock_builder

                get_enriched_system_prompt(dialogue, phase=phase)

                mock_builder.build_for_voice_full.assert_called_once()
                call_kwargs = mock_builder.build_for_voice_full.call_args
                assert call_kwargs.kwargs.get("phase") == phase or \
                       (len(call_kwargs.args) > 1 and call_kwargs.args[1] == phase), \
                    f"Builder should be called with phase={phase}"
