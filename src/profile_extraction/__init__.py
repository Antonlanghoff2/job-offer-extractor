# Copyright Anton Langhoff
# SPDX-License-Identifier: MIT

"""Services d'extraction dédiés au profil utilisateur."""

from .experience_skill_extractor import extract_skills_from_experience

__all__ = ["extract_skills_from_experience"]
