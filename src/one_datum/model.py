# -*- coding: utf-8 -*-

__all__ = ["RVErrorModel", "DR2RVErrorModel", "BasicDR2RVErrorModel"]

from typing import Optional, Tuple

import kepler
import numpy as np
import scipy.stats


class RVErrorModel:
    def __init__(
        self,
        num_transits: int,
        num_samples: int,
        seed: Optional[int] = None,
    ):
        self.num_transits = num_transits
        self.num_samples = num_samples

        random = np.random.default_rng(seed)
        self.epsilon = random.standard_normal(num_samples)
        self.time_samples = self.sample_times(
            random, num_samples, num_transits
        )
        self.parameter_samples, self.fiducial_model = self.sample_parameters(
            random, self.time_samples
        )
        self.rate_parameter = np.sum(
            (
                self.fiducial_model
                - np.mean(self.fiducial_model, axis=0)[None, :]
            )
            ** 2,
            axis=0,
        )

    def sample_parameters(
        self, random: np.random.Generator, times: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        raise NotImplementedError("Must be implemented by subclasses")

    def sample_times(
        self,
        random: np.random.Generator,
        num_samples: int,
        num_transits: int,
    ) -> np.ndarray:
        raise NotImplementedError("Must be implemented by subclasses")

    def compute_fiducial_model(
        self,
        times: np.ndarray,
        *,
        semiamp: np.ndarray,
        period: np.ndarray,
        phase: np.ndarray,
        ecc: Optional[np.ndarray] = None,
        omega: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        mean_anom = 2 * np.pi * times / period[None, :] + phase[None, :]

        if ecc is None:
            assert omega is None
            return semiamp * np.cos(mean_anom)

        assert omega is not None
        cosw = np.cos(omega)
        sinw = np.sin(omega)
        _, cosf, sinf = kepler.kepler(
            mean_anom, ecc[None, :] + np.zeros_like(mean_anom)
        )
        return semiamp * (
            cosw[None, :] * (ecc[None, :] + cosf) - sinw[None, :] * sinf
        )

    def __call__(
        self,
        sample_variance: float,
        log_sigma: float,
        log_sigma_error: Optional[float] = None,
    ) -> np.ndarray:
        if log_sigma_error is None:
            sigma = np.exp(log_sigma)
        else:
            sigma = np.exp(log_sigma + log_sigma_error * self.epsilon)
        ivar = 1.0 / sigma ** 2
        rate = self.rate_parameter
        ncx2 = scipy.stats.ncx2(df=self.num_transits, nc=rate)
        return ncx2.logpdf((self.num_transits - 1) * sample_variance * ivar)


class DR2RVErrorModel(RVErrorModel):
    def sample_times(
        self,
        random: np.random.Generator,
        num_samples: int,
        num_transits: int,
    ) -> np.ndarray:
        return random.uniform(0, 668.0, (num_transits, num_samples))


class BasicDR2RVErrorModel(DR2RVErrorModel):
    def __init__(
        self,
        num_transits: int,
        num_samples: int,
        log_period_range: Tuple[float, float] = (1.0, 800.0),
        log_semiamp_range: Tuple[float, float] = (0.1, 100.0),
        ecc_params: Optional[Tuple[float, float]] = None,
        ecc_uniform: bool = False,
        seed: Optional[int] = None,
    ):
        self.log_period_range = log_period_range
        self.log_semiamp_range = log_semiamp_range
        self.ecc_params = ecc_params
        self.ecc_uniform = ecc_uniform
        super().__init__(num_transits, num_samples, seed)

    def sample_parameters(
        self, random: np.random.Generator, times: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        num_samples = times.shape[1]

        log_period = random.uniform(
            self.log_period_range[0], self.log_period_range[1], num_samples
        )
        log_semiamp = random.uniform(
            self.log_semiamp_range[0],
            self.log_semiamp_range[1],
            num_samples,
        )
        phase = random.uniform(-np.pi, np.pi, num_samples)

        if self.ecc_params is None:
            params = np.concatenate(
                (log_semiamp[:, None], log_period[:, None], phase[:, None]),
                axis=1,
            )
            mod = self.compute_fiducial_model(
                times,
                semiamp=np.exp(log_semiamp),
                period=np.exp(log_period),
                phase=phase,
            )
        else:
            if self.ecc_uniform:
                ecc = random.uniform(
                    self.ecc_params[0], self.ecc_params[1], num_samples
                )
            else:
                ecc = random.beta(
                    self.ecc_params[0], self.ecc_params[1], num_samples
                )
            omega = random.uniform(-np.pi, np.pi, num_samples)
            params = np.concatenate(
                (
                    log_semiamp[:, None],
                    log_period[:, None],
                    phase[:, None],
                    ecc[:, None],
                    omega[:, None],
                ),
                axis=1,
            )
            mod = self.compute_fiducial_model(
                times,
                semiamp=np.exp(log_semiamp),
                period=np.exp(log_period),
                phase=phase,
                ecc=ecc,
                omega=omega,
            )

        return params, mod
