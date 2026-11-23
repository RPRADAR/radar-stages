"""Erreurs particulières du robot."""


class SourceIgnoree(Exception):
    """La source ne peut pas être lue pour l'instant (par exemple : limite de requêtes du site).
    Ce n'est pas une panne : le robot continue, et le signale simplement dans l'email."""
