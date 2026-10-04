import numpy as np
import math

class PolyolefinReactor:
    def __init__(self, dt=1.0, bed_mass=100000, production_rate=40000):
        self.dt = dt
        self.bed_mass = bed_mass
        self.production_rate = production_rate
        self.tau = (self.bed_mass / self.production_rate) * 60.0  # residence time in minutes
        
        self.A = 88.0
        self.B = 3.40
        
        self.grades = {
            'A': {'MFI': 0.3, 'density': 0.949, 'H2_M': 0.05},
            'B': {'MFI': 8.0, 'density': 0.954, 'H2_M': 0.35},
            'C': {'MFI': 1.0, 'density': 0.918, 'H2_M': 0.10}
        }
        
        self.time = 0.0
        self.H2_M_ratio = 0.0
        self.MFI_bed = 0.0
        self.MFI_inst = 0.0
        self.Mw_bed = 0.0
        self.T_bed = 350.0 
        
        self.reset('A')

    def calc_MFI_from_Mw(self, Mw):
        try:
            ln_MFI = self.A - self.B * math.log(Mw)
            ln_MFI = max(min(ln_MFI, 20.0), -10.0)
            return math.exp(ln_MFI)
        except:
            return 1.0

    def calc_Mw_from_MFI(self, MFI):
        return math.exp((self.A - math.log(MFI)) / self.B)

    def get_instantaneous_properties(self, H2_M_ratio):
        # MFI = 74.34 * (H2_M)^2 + 6.77 * (H2_M) - 0.22 (approx fit)
        MFI_inst = max(0.01, 74.34 * H2_M_ratio**2 + 6.77 * H2_M_ratio - 0.22)
        Mw_inst = self.calc_Mw_from_MFI(MFI_inst)
        return MFI_inst, Mw_inst

    def reset(self, initial_grade='A'):
        grade_info = self.grades[initial_grade]
        self.H2_M_ratio = grade_info['H2_M']
        self.MFI_inst, self.Mw_bed = self.get_instantaneous_properties(self.H2_M_ratio)
        self.MFI_bed = grade_info['MFI']
        self.time = 0.0
        return self._get_obs()

    def step(self, H2_M_setpoint):
        tau_gas = 10.0
        dH2M_dt = (H2_M_setpoint - self.H2_M_ratio) / tau_gas
        self.H2_M_ratio += dH2M_dt * self.dt
        
        self.MFI_inst, Mw_inst = self.get_instantaneous_properties(self.H2_M_ratio)
        
        dMw_dt = (Mw_inst - self.Mw_bed) / self.tau
        self.Mw_bed += dMw_dt * self.dt
        self.MFI_bed = self.calc_MFI_from_Mw(self.Mw_bed)
        
        self.T_bed = 350.0 + np.random.normal(0, 0.5)
        self.time += self.dt
        
        return self._get_obs()
        
    def _get_obs(self):
        return {
            'time': self.time,
            'H2_M_ratio': self.H2_M_ratio,
            'MFI_inst': self.MFI_inst,
            'MFI_bed': self.MFI_bed,
            'T_bed': self.T_bed,
            'production_rate': self.production_rate
        }
