"""Module with a class for Lufft chm15k ceilometer."""
import logging

import netCDF4
from numpy import ma

from cloudnetpy import utils
from cloudnetpy.instruments import instruments
from cloudnetpy.instruments.nc_lidar import NcLidar


class LufftCeilo(NcLidar):
    """Class for Lufft chm15k ceilometer."""

    serial_number: str | None

    def __init__(
        self, file_name: str, site_meta: dict, expected_date: str | None = None
    ):
        super().__init__()
        self.file_name = file_name
        self.site_meta = site_meta
        self.expected_date = expected_date
        self.serial_number = None

    def read_ceilometer_file(self, calibration_factor: float | None = None) -> None:
        """Reads data and metadata from Jenoptik netCDF file."""
        with netCDF4.Dataset(self.file_name) as dataset:
            self.dataset = dataset
            self._fetch_attributes()
            self._fetch_range(reference="upper")
            self._fetch_beta_raw(calibration_factor)
            self._fetch_time_and_date()
            self._fetch_zenith_angle("zenith")

    def _fetch_beta_raw(self, calibration_factor: float | None = None) -> None:
        assert self.dataset is not None
        if calibration_factor is None:
            logging.warning("Using default calibration factor")
            calibration_factor = 3e-12
        beta_raw = self._getvar("beta_raw", "beta_att")
        old_version = self._get_old_software_version()
        if old_version is not None:
            logging.warning(
                f"Software version {old_version}. Assuming data not range corrected."
            )
            data_std = self._getvar("stddev")
            normalised_apd = self._get_nn()
            beta_raw *= utils.transpose(data_std / normalised_apd)
            beta_raw *= self.data["range"] ** 2
        beta_raw *= calibration_factor
        self.data["calibration_factor"] = float(calibration_factor)
        self.data["beta_raw"] = beta_raw

    def _get_old_software_version(self) -> str | None:
        assert self.dataset is not None
        version = self.dataset.software_version
        if len(str(version)) > 4:
            return None
        return version

    def _get_nn(self):
        nn1 = self._getvar("nn1", "NN1")
        median_nn1 = ma.median(nn1)
        # Parameters taken from the matlab code and should be verified
        if 120 < median_nn1 < 160:
            step_factor, reference, scale = 1.24, 140, 5
        elif 3200 < median_nn1 < 4000:
            step_factor, reference, scale = 1.035, 3685, 1
        else:
            logging.warning("Unable to compute normalized APD")
            return 1
        return step_factor ** (-(nn1 - reference) / scale)

    def _getvar(self, *args):
        assert self.dataset is not None
        for arg in args:
            if arg in self.dataset.variables:
                var = self.dataset.variables[arg]
                return var[0] if utils.isscalar(var) else var[:]
        raise ValueError("Unknown variable")

    def _fetch_attributes(self):
        self.serial_number = getattr(self.dataset, "device_name", None)
        if self.serial_number is None:
            self.serial_number = getattr(self.dataset, "source")
        self.instrument = (
            instruments.CHM15KX
            if self.serial_number.startswith("CHX")
            else instruments.CHM15K
        )
