# Copyright Anton Langhoff <anton@langhoff.fr>
# SPDX-License-Identifier: MIT

"""
job_offer_extractor – Extracts structured information from raw French job offers.

Modules
-------
preprocessing      : Text cleaning and segmentation.
feature_extraction : TF-IDF vectorisation and feature engineering.
train_classifier   : Training pipeline for the segment classifier.
extractors         : Rule-based post-processing extractors.
predict            : High-level prediction API.
evaluate           : Evaluation and reporting utilities.
"""

__version__ = "1.0.0"
