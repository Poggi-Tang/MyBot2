import unittest

from mybot_ui.realtime_tools import (
    RealtimeToolExecutor,
    _weather_location,
    _weather_reply,
    detect_realtime_request,
)


class RealtimeToolTests(unittest.TestCase):
    def test_detects_weather_time_and_contextual_tool_followup(self):
        weather = detect_realtime_request("上海徐汇今天天气怎么样")
        current_time = detect_realtime_request("你看看现在几点")
        followup = detect_realtime_request(
            "你用 agent 去查",
            "对方: 上海徐汇今天天气怎么样\nMyBot: 暂时查不到",
        )

        self.assertEqual("weather", weather.kind)
        self.assertEqual("time", current_time.kind)
        self.assertEqual("weather", followup.kind)
        self.assertEqual("上海徐汇今天天气怎么样", followup.query)

    def test_detects_short_forecast_followup_from_weather_context(self):
        followup = detect_realtime_request(
            "明天呢",
            "芝士圆子: 闵行今天天气怎么样\n圆子: 闵行现在 26℃，最高降雨概率约 93%",
        )

        self.assertIsNotNone(followup)
        self.assertEqual("weather", followup.kind)
        self.assertEqual("闵行今天天气怎么样 明天呢", followup.query)

    def test_extracts_weather_location(self):
        self.assertEqual("上海徐汇", _weather_location("上海徐汇今天天气怎么样"))
        self.assertEqual("北京朝阳", _weather_location("帮我查北京朝阳的天气"))
        self.assertEqual("上海", _weather_location("今天天气怎么样"))
        self.assertEqual("闵行", _weather_location("明天闵行天气怎么样"))
        self.assertEqual("上海", _weather_location("@圆子\u2005上海今天天气怎么样"))

    def test_formats_weather_payload(self):
        payload = {
            "current_condition": [{
                "temp_C": "34",
                "FeelsLikeC": "39",
                "humidity": "49",
                "weatherCode": "176",
                "localObsDateTime": "2026-08-08 12:01 PM",
            }],
            "weather": [{
                "mintempC": "28",
                "maxtempC": "35",
                "hourly": [{"chanceofrain": "20"}, {"chanceofrain": "70"}],
            }],
        }

        result = _weather_reply(payload, "上海徐汇")

        self.assertIn("我刚看了下", result)
        self.assertIn("现在 34 度", result)
        self.assertIn("28 到 35 度", result)
        self.assertIn("出门记得带伞", result)
        self.assertNotIn("wttr.in", result)
        self.assertNotIn("数据源", result)

    def test_current_weather_does_not_expose_source_observation_fields(self):
        payload = {
            "current_condition": [{
                "temp_C": "26",
                "FeelsLikeC": "26",
                "humidity": "94",
                "weatherCode": "353",
                "observation_time": "01:33 PM",
            }],
            "weather": [{
                "mintempC": "25",
                "maxtempC": "27",
                "hourly": [{"chanceofrain": "93"}],
            }],
        }

        result = _weather_reply(payload, "闵行")

        self.assertIn("我刚看了下", result)
        self.assertNotIn("01:33 PM", result)
        self.assertNotIn("北京时间", result)
        self.assertNotIn("观测", result)
        self.assertNotIn("wttr.in", result)
        self.assertNotIn("~", result)

    def test_formats_tomorrow_forecast_instead_of_current_conditions(self):
        payload = {
            "current_condition": [{"temp_C": "26", "FeelsLikeC": "26", "humidity": "94"}],
            "weather": [
                {"mintempC": "25", "maxtempC": "27", "hourly": []},
                {
                    "mintempC": "24",
                    "maxtempC": "30",
                    "hourly": [{"chanceofrain": "60", "weatherCode": "296"}],
                },
            ],
        }

        result = _weather_reply(payload, "闵行", query="闵行今天天气怎么样 明天呢")

        self.assertIn("闵行明天大概 24 到 30 度", result)
        self.assertIn("小雨", result)
        self.assertIn("带把伞", result)
        self.assertNotIn("当前", result)
        self.assertNotIn("最新预报", result)
        self.assertNotIn("wttr.in", result)

    def test_time_tool_uses_conversational_wording(self):
        result = RealtimeToolExecutor()._time()
        self.assertIn("现在", result)
        self.assertIn("今天星期", result)
        self.assertNotIn("北京时间", result)
        self.assertNotIn("秒", result)


if __name__ == "__main__":
    unittest.main()
