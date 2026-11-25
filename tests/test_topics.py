import unittest

import presentation


class TopicClassificationTests(unittest.TestCase):
    def test_every_topic_is_reachable(self):
        """Each topic must be able to claim at least one plausible title."""
        samples = {
            "氧运输与心肺整合": "Cardiac output and arterial function during steady-state cycling",
            "骨骼肌代谢与线粒体功能": "Skeletal muscle mitochondrial function after endurance training",
            "强度阈值、临界功率与耐力表现": "Critical power and lactate threshold in trained runners",
            "力量、爆发力与神经肌肉": "Neuromuscular fatigue after maximal strength training",
            "免疫、炎症与分子适应": "Exercise-induced inflammation and cytokine response",
            "训练干预与周期化": "Periodization of training load in elite swimmers",
            "疲劳、恢复与竞技表现": "Overreaching, recovery and readiness in competitive athletes",
            "测试、评估与运动表现": "Reliability of a field test for sprint performance",
            "生物力学、技术与装备": "Joint kinetics and footwear during running",
            "竞技与比赛分析": "Match load and tactical performance in professional football",
            "可穿戴与运动监测": "Wearable accelerometer and global positioning data in training",
            "数据建模与算法": "Machine learning model for predicting race performance",
            "测量方法与效度": "Measurement validity and intra-rater reliability of a sensor",
            "环境生理与特殊场景": "Thermoregulation and heat strain during exercise in the heat",
            "特殊人群与生命周期": "Muscle function in older adults after resistance training",
            "肌肉骨骼、损伤与康复": "Return to sport after anterior cruciate ligament injury",
            "营养、补剂与能量可用性": "Creatine supplementation and energy availability in athletes",
            "脑认知、心理健康与行为": "Executive function and mood after acute exercise",
            "体力活动、公共卫生与人群干预": "Physical activity and mortality in a population cohort",
        }
        for topic, title in samples.items():
            self.assertIn(topic, presentation.PATTERNS)
            self.assertEqual(presentation.topic_for({"title": title, "topics": ()}), topic, title)

    def test_notices_stay_out_of_research_topics(self):
        for title in ("Correction to: Effects of exercise on blood pressure",
                      "Erratum: Training load and injury risk"):
            self.assertEqual(presentation.topic_for({"title": title, "topics": ()}),
                             presentation.PUBLICATION_NOTICE)

    def test_unclassifiable_title_falls_back_to_other(self):
        self.assertEqual(
            presentation.topic_for({"title": "Table 3: study characteristics",
                                    "topics": ()}),
            presentation.OTHER,
        )

    def test_journal_topic_tag_pushes_the_paper_to_that_topic(self):
        title = "A new instrument for measuring running economy"
        self.assertEqual(
            presentation.topic_for({"title": title, "topics": ("可穿戴运动监测",)}),
            "可穿戴与运动监测",
        )


if __name__ == "__main__":
    unittest.main()
