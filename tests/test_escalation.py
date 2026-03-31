import unittest
from unittest.mock import patch, MagicMock
from pipeline.escalation import resolve_plate_escalation

class TestResolvePlateEscalation(unittest.TestCase):

    def setUp(self):
        self.default_stats = {
            "format_bias_triggers": 0,
            "gemini_flash_image_calls": 0,
            "format_bias_gemini_calls": 0,
            "format_bias_state_corrections": 0,
            "format_bias_brute_force_queries": 0,
            "format_bias_brute_force_hits": 0,
            "ocr_sub_attempts": 0,
            "ocr_sub_hits": 0,
            "ocr_sub_fallbacks": 0
        }
    
    def test_phase0_short_circuit(self):
        # Already Y match on entry
        stats = self.default_stats.copy()
        
        # We don't need to mock anything because it should immediately return
        plate, state, r_found, desc, vin, title, match, final_stats, db_cache = resolve_plate_escalation(
            plate="ABC1234", clean_state="MN", db_cache={}, db_cache_file="dummy.json",
            stats=stats, obs_words={"honda", "civic", "blue"}, best_frame="frame.jpg",
            reg_found=True, info_desc="2010 Honda Civic Blue", vin="12345", title="Clean",
            match_status="Y", initial_plate="ABC1234", initial_state="MN"
        )

        self.assertEqual(match, "Y")
        self.assertTrue(r_found)
        # Verify stats are unmodified
        self.assertEqual(final_stats["format_bias_triggers"], 0)

    @patch("pipeline.escalation.is_valid_format")
    @patch("pipeline.escalation.get_candidate_states")
    @patch("pipeline.escalation.format_bias_reeval")
    @patch("pipeline.escalation.try_registration")
    def test_phaseA5_strategy1_short_circuit(self, mock_try_reg, mock_fb_reeval, mock_cand, mock_is_valid):
        stats = self.default_stats.copy()
        mock_is_valid.return_value = False
        mock_cand.return_value = ["WI", "IL"]
        
        # Mock Gemini finding a better format
        mock_fb_reeval.return_value = ("WI", "ABC123")
        
        # Mock DMV hitting on the Gemini corrected state
        mock_try_reg.return_value = {
            "registration_found": True,
            "desc": "2010 Honda Civic Blue",
            "vin": "5678"
        }

        plate, state, r_found, desc, vin, title, match, final_stats, db_cache = resolve_plate_escalation(
            plate="ABC1234", clean_state="MN", db_cache={}, db_cache_file="dummy.json",
            stats=stats, obs_words={"honda", "civic", "blue"}, best_frame="frame.jpg",
            reg_found=False, info_desc="", vin="", title="",
            match_status="", initial_plate="ABC1234", initial_state="MN"
        )

        self.assertEqual(match, "Y")
        self.assertEqual(state, "WI")
        self.assertEqual(plate, "ABC123")
        self.assertEqual(final_stats["format_bias_state_corrections"], 1)
        mock_try_reg.assert_called_once_with("ABC123", "WI", {}, "dummy.json")

    @patch("pipeline.escalation.is_valid_format")
    @patch("pipeline.escalation.get_candidate_states")
    @patch("pipeline.escalation.format_bias_reeval")
    @patch("pipeline.escalation.try_registration")
    def test_phaseA5_strategy2_short_circuit(self, mock_try_reg, mock_fb_reeval, mock_cand, mock_is_valid):
        stats = self.default_stats.copy()
        mock_is_valid.return_value = False
        mock_cand.return_value = ["IA", "ND"]
        mock_fb_reeval.return_value = (None, None) # Strategy 1 yields nothing
        
        def try_reg_side_effect(p, s, cache, c_file):
            if s == "ND":
                return {"registration_found": True, "desc": "2010 Honda Civic Blue", "vin": "NDVIN"}
            return {"registration_found": False}
        mock_try_reg.side_effect = try_reg_side_effect

        plate, state, r_found, desc, vin, title, match, final_stats, db_cache = resolve_plate_escalation(
            plate="ABC1234", clean_state="MN", db_cache={}, db_cache_file="dummy.json",
            stats=stats, obs_words={"honda", "civic", "blue"}, best_frame="frame.jpg",
            reg_found=False, info_desc="", vin="", title="",
            match_status="", initial_plate="ABC1234", initial_state="MN"
        )

        self.assertEqual(match, "Y")
        self.assertEqual(state, "ND")
        self.assertEqual(final_stats["format_bias_brute_force_hits"], 1)

    @patch("pipeline.escalation.is_valid_format")
    @patch("pipeline.escalation.gemini_flash_confirm_plate")
    @patch("pipeline.escalation.try_registration")
    def test_phaseB_confirm_mismatch_short_circuit(self, mock_try_reg, mock_confirm, mock_is_valid):
        stats = self.default_stats.copy()
        mock_is_valid.return_value = True
        
        # Mock Gemini confirming plate was misread
        mock_confirm.return_value = "OBC123"
        
        mock_try_reg.return_value = {
            "registration_found": True,
            "desc": "2010 Honda Civic Blue",
            "vin": "OBCVIN"
        }

        # Enter with a mismatch from Phase 0
        plate, state, r_found, desc, vin, title, match, final_stats, db_cache = resolve_plate_escalation(
            plate="QBC123", clean_state="MN", db_cache={}, db_cache_file="dummy.json",
            stats=stats, obs_words={"honda", "civic", "blue"}, best_frame="frame.jpg",
            reg_found=True, info_desc="2015 Ford Fiesta Red", vin="QBCVIN", title="",
            match_status="N", initial_plate="QBC123", initial_state="MN"
        )

        self.assertEqual(match, "Y")
        self.assertEqual(plate, "OBC123")
        self.assertTrue(r_found)

    @patch("pipeline.escalation.is_valid_format")
    @patch("pipeline.escalation.gemini_flash_confirm_plate")
    @patch("pipeline.escalation.gemini_flash_reeval")
    @patch("pipeline.escalation.generate_substitution_candidates")
    @patch("pipeline.escalation.try_neighboring_states")
    def test_fallback_mismatch(self, mock_neigh, mock_sub, mock_reeval, mock_confirm, mock_is_valid):
        """Test that if nothing yields Y, we fallback to the highest quality N match."""
        stats = self.default_stats.copy()
        mock_is_valid.return_value = True
        mock_confirm.return_value = "ORIG123"
        mock_reeval.return_value = (None, None)
        mock_sub.return_value = []
        mock_neigh.return_value = (None, None)

        plate, state, r_found, desc, vin, title, match, final_stats, db_cache = resolve_plate_escalation(
            plate="ORIG123", clean_state="MN", db_cache={}, db_cache_file="dummy.json",
            stats=stats, obs_words={"honda", "civic"}, best_frame="frame.jpg",
            reg_found=True, info_desc="1999 Chevy Malibu", vin="CHEVYVIN", title="",
            match_status="N", initial_plate="ORIG123", initial_state="MN"
        )

        self.assertEqual(match, "N")
        self.assertEqual(plate, "ORIG123")
        self.assertEqual(desc, "1999 Chevy Malibu")
        self.assertEqual(final_stats["ocr_sub_fallbacks"], 1)

if __name__ == '__main__':
    unittest.main()
