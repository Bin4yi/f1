class MonteCarloSimulator:
    """
    Monte Carlo simulator for F1 race scenarios.
    """
    def __init__(self, n_simulations: int = 1000):
        self.n_simulations = n_simulations

    def run_simulation(self, context: dict) -> dict:
        """
        Run simulations based on the provided context.
        """
        # Placeholder for real simulation logic
        return {"probability_of_overtake": 0.65, "simulations_run": self.n_simulations}
