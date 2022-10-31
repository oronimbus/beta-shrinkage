"""Feature different approaches to calculating security betas. 

References:
-----------
    Blitz, David, Laurens Swinkels, Kristina Ūsaitė, and Pim van Vliet. 'Shrinking Beta'. 
        SSRN Scholarly Paper. Rochester, NY, 10 February 2022.
    Blume, Marshall E. 'Betas and Their Regression Tendencies'. The Journal of Finance 30,
        no. 3 (1975): 785-95.
    Frazzini, Andrea, and Lasse Heje Pedersen. 'Betting against Beta'. Journal of Financial
        Economics 111, no. 1 (1 January 2014): 1-25.
    Hollstein, Fabian, Marcel Prokopczuk, and Chardin Wese Simen. 'Estimating Beta: Forecast
        Adjustments and the Impact of Stock Characteristics for a Broad Cross-Section'.
        SSRN Scholarly Paper. Rochester, NY, 17 August 2018.
    Scholes, Myron, and Joseph Williams. 'Estimating Betas from Nonsynchronous Data'.
        Journal of Financial Economics 5, no. 3 (1 December 1977): 309-27.
    Welch, Ivo. 'Simply Better Market Betas'. SSRN Scholarly Paper. Rochester, NY, 13 June 2021. 
    Vasicek, Oldrich A. 'A Note on Using Cross-Sectional Information in Bayesian Estimation of
        Security Betas'. The Journal of Finance 28, no. 5 (December 1973): 1233-39.
"""
from itertools import chain, combinations
import numpy as np


def add_intercept(data):
    """Add column vector of ones to front of matrix."""
    return np.hstack([np.ones((data.shape[0], 1)), data])


class Beta:
    def __init__(self, exog, endog):
        self.exog = np.atleast_2d(exog).T
        self.endog = np.atleast_2d(endog).T
        self.n_obs = exog.shape[0]
        self.exog_mat = np.hstack([np.ones((self.n_obs, 1)), self.exog])

    def _weighted_ols(
        self, X: np.array, y: np.array, w: np.array = None, demean: bool = False
    ) -> np.array:
        """Helper class to calculate beta using WLS.

        Args:
            X (np.array): exogeneous variable (e.g. SPY)
            y (np.array): endogeneous variable (e.g. AAPL)
            w (np.array, optional): vector of weights. Defaults to None.
            demean (bool, optional): subtract mean from ``X``. Defaults to False.

        Returns:
            np.array: vector of betas
        """
        if demean:
            X -= np.mean(X, axis=0)

        if w is None:
            w = np.ones(X.shape[0])
        w = np.diag(w)
        return np.linalg.inv(X.T @ w @ X) @ X.T @ w @ y

    def ols(self, adjusted: bool = False) -> float:
        """Classic beta calculation using OLS.

        Beta can be shrunk towards unity using Merril Lynch approach. This is the same
        as Blume (1975).

        Args:
            adjusted (bool, optional): shrink towards unity. Defaults to False.

        Returns:
            float: beta
        """
        beta = np.ravel(self._weighted_ols(self.exog_mat, self.endog))[-1]
        if adjusted:
            return 0.67 * beta + 0.33
        return beta

    def vasicek(self, beta_prior: float = 1, se_prior: float = 0.5) -> float:
        """Bayesian estimation of beta using Vasicek (1973).

        Args:
            beta_prior (float, optional): _description_. Defaults to 1.
            se_prior (float, optional): _description_. Defaults to 0.5.

        Returns:
            float: Vasicek beta
        """
        beta = self._weighted_ols(self.exog_mat, self.endog)
        endog_hat = self.exog_mat @ beta
        s_yy = np.sum(np.square(self.endog - endog_hat)) / (self.n_obs - 2)
        s_xx = np.sum(np.square(self.exog - np.mean(self.exog)))
        std_error = np.sqrt(s_yy / s_xx)

        # Bayesian estimation of marginal posterior
        num = beta_prior / np.square(se_prior) + beta[1] / np.square(std_error)
        den = 1 / np.square(se_prior) + 1 / np.square(std_error)
        return np.ravel(num / den)[0]

    def welch(self, delta: float = 3, rho: float = 0) -> float:
        """Slope winsorized beta using Welch (2021).

        A decay factor ``rho`` can be chosen such that more relevance is given
        to more recent observation. The paper uses ``2/256`` as an exponential
        decay factor.

        Args:
            delta (float, optional): winsorisation parameter. Defaults to 3.
            rho (float, optional): decay factor. Defaults to 0.

        Returns:
            float: Welch beta
        """
        bm_min, bm_max = (1 - delta) * self.exog, (1 + delta) * self.exog
        lower, upper = np.minimum(bm_min, bm_max), np.maximum(bm_min, bm_max)
        endog_wins = np.atleast_2d(np.clip(self.endog, lower, upper))
        weights = np.exp(-rho * np.arange(self.n_obs)[::-1])
        beta = self._weighted_ols(self.exog_mat, endog_wins, w=weights)
        return np.ravel(beta)[1]

    def robeco(
        self, corr_target: float, vol_target: float, gamma: float = 0.5, phi: float = 0.2
    ) -> float:
        """Beta shrinkage using Blitz et al. (2022).

        The Robeco beta is calculated using the correlation of asset to market returns and the
        ratio of their volatilties separately. Both are shrunk towards a cross-sectional mean.
        The beta is the product of the correlation and the volatility ratio.

        Args:
            corr_target (float): cross sectional mean of correlation
            vol_target (float): cross sectional mean of volatility ratio
            gamma (float, optional): correlation shrinkage factor. Defaults to 0.5.
            phi (float, optional): volatility ratio shrinkage factor. Defaults to 0.2.

        Returns:
            float: Robeco beta
        """
        corr = np.corrcoef(self.exog.T, self.endog.T)[0, 1]
        corr_shrink = (1 - gamma) * corr + gamma * corr_target
        vol_ratio = np.std(self.endog) / np.std(self.exog)
        vol_shrink = (1 - phi) * vol_ratio + phi * vol_target
        beta = corr_shrink * vol_shrink
        return beta

    def scholes_williams(self) -> float:
        """Calculate shrunk beta using Scholes & Williams (1977)."""
        beta_lead = np.ravel(self._weighted_ols(self.exog_mat[1:, :], self.endog[:-1, :]))[-1]
        beta_lag = np.ravel(self._weighted_ols(self.exog_mat[:-1, :], self.endog[1:, :]))[-1]
        beta = np.ravel(self._weighted_ols(self.exog_mat, self.endog))[-1]
        auto_corr = np.corrcoef(self.exog[1:, :], self.exog[:-1, :], rowvar=False)[0, 1]

        beta = (beta_lag + beta + beta_lead) / (1 + 2 * auto_corr)
        return beta


class BetaForecastCombination:
    def __init__(self, exog: np.array, endog: np.array, window: int = 21):
        self.exog = np.atleast_2d(exog).T
        self.endog = np.atleast_2d(endog).T
        self.window = window
        self.n_obs = self.endog.shape[0]
        self.weights = None

    def _generate_estimation_windows(self, data: np.array) -> list:
        return [data[: self.window + i] for i in range(data.shape[0] - self.window)]

    def _generate_betas(self, windows: list, **kwargs: dict) -> np.array:
        # set up iterator
        beta_obj = [Beta(i[:, 0], i[:, 1]) for i in windows]
        c, v = kwargs.get("corr_target", 0.5), kwargs.get("vol_target", 2)

        # consumer iterator and cast into 2d numpy array
        ols = np.atleast_2d(list(map(lambda x: x.ols(), beta_obj))).T
        adj_ols = np.atleast_2d(list(map(lambda x: x.ols(True), beta_obj))).T
        vasicek = np.atleast_2d(list(map(lambda x: x.vasicek(), beta_obj))).T
        welch = np.atleast_2d(list(map(lambda x: x.welch(), beta_obj))).T
        aged_welch = np.atleast_2d(list(map(lambda x: x.welch(rho=2 / 256), beta_obj))).T
        robeco = np.atleast_2d(list(map(lambda x: x.robeco(c, v), beta_obj))).T
        # schol_will = np.atleast_2d(list(map(lambda x: x.scholes_williams(), beta_obj))).T

        return np.hstack([ols, adj_ols, vasicek, welch, aged_welch, robeco])

    def fit(self) -> float:
        # split training data from test data for parameter estimation
        cutoff = self.n_obs - self.window
        train_data = np.hstack([self.exog[:cutoff, :], self.endog[:cutoff, :]])
        test_data = np.hstack([self.exog[cutoff:, :], self.endog[cutoff:, :]])

        # calculate beta using expanding window
        training_windows = self._generate_estimation_windows(train_data)
        betas = self._generate_betas(training_windows)

        # regress betas onto realised betas
        one = np.ones([train_data.shape[0] - self.window - 1, 1])
        X_train = add_intercept(betas[:-1, :])
        self.weights = np.linalg.pinv(X_train) @ betas[1:, 0]

        # project weights onto test data
        betas_test = self._generate_betas([test_data])
        X_test = add_intercept(betas_test)
        return np.ravel(X_test @ self.weights)[0]


class BetaBMA(BetaForecastCombination):
    def __init__(self, exog: np.array, endog: np.array, window: int = 21, shrinkage: float = None):
        super().__init__(exog, endog)
        self.shrinkage = shrinkage
        
    def _generate_beta_combinations(self, data):
        indices = list(range(data.shape[0]))
        combos = [list(combinations(indices, i)) for i in range(1, data.shape[0])]
        return list(chain(*combos))  
            
    def fit(self, dof_r: int = 1):
        # estimation windows for prior
        data_matrix = np.hstack([self.exog, self.endog])
        training_windows = self._generate_estimation_windows(data_matrix)
        beta_w = self._generate_betas(training_windows)
        beta_s = add_intercept(self._generate_betas([data_matrix]))

        # retrieve all beta estimates and possible combinations
        combos = self._generate_beta_combinations(beta_w[0])
        
        # set up model inputs
        g = 1 / min(len(training_windows), len(combos))
        a_g = g / (1 + g)
        
        # step 1: restricted model
        beta_r = add_intercept(beta_w[:-dof_r, [0]])
        b_r_hat = np.linalg.pinv(beta_r) @ beta_w[dof_r:, [0]]
        y_r_hat = beta_r @ b_r_hat
        ssr_r = np.sum(np.square(beta_w[dof_r:, [0]] - y_r_hat))
        
        # step 2: iterate over beta combinations, store as list of tuples
        models = []
        for combo in combos:
            # calculate SSR_u first using lagged realised betas
            beta_u = add_intercept(beta_w[:-1, combo])
            b_u_hat = np.linalg.pinv(beta_u) @ beta_w[1:, [0]]
            y_u_hat = beta_u @ b_u_hat
            ssr_u = np.sum(np.square(beta_w[1:, [0]] - y_u_hat))
            
            # project combined beta onto series of realised betas
            weights = np.zeros((beta_w.shape[1] + 1, 1))
            weights[0, :] = b_u_hat[0,:]
            weights[np.array(combo) + 1, :] = b_u_hat[1:,:]
            beta_k = np.ravel(beta_s @ weights)[0]
            models.append((len(combo), beta_k, ssr_u))
            
        # step 3: calculate beta weights
        w_k = []
        for p, _, ssr in models:
            w_k.append([np.power(a_g, 0.5 * p) * np.power(1 + 1 / g * ssr / ssr_r, -0.5 * dof_r)])
        w_final = np.array([w / np.sum(w_k) for w in w_k])
        
        # step 4: combine weights with betas for final estimate
        beta_bma = np.sum(np.array(models)[:,1] * w_final)
            
        return beta_bma