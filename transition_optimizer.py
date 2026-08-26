import numpy as np
from scipy.optimize import minimize_scalar
from reactor_simulator import PolyolefinReactor

class TransitionOptimizer:
    def __init__(self, initial_grade='A', target_grade='B', prod_rate=40000):
        self.initial_grade = initial_grade
        self.target_grade = target_grade
        self.prod_rate = prod_rate
        self.env = PolyolefinReactor(dt=1.0, production_rate=prod_rate)
        
        self.target_MFI = self.env.grades[target_grade]['MFI']
        self.target_H2M = self.env.grades[target_grade]['H2_M']
        self.initial_MFI = self.env.grades[initial_grade]['MFI']
        
        self.spec_band = 0.05

    def is_on_spec(self, mfi):
        return (self.target_MFI * (1 - self.spec_band) <= mfi <= self.target_MFI * (1 + self.spec_band))

    def simulate_linear_ramp(self, ramp_time_min=240.0, sim_time_min=600.0):
        self.env.reset(self.initial_grade)
        
        history = {'time': [], 'H2_M': [], 'MFI_inst': [], 'MFI_bed': [], 'on_spec': []}
        start_H2M = self.env.H2_M_ratio
        
        for t in range(int(sim_time_min)):
            if t < ramp_time_min:
                setpoint = start_H2M + (self.target_H2M - start_H2M) * (t / ramp_time_min)
            else:
                setpoint = self.target_H2M
                
            obs = self.env.step(setpoint)
            
            history['time'].append(obs['time'])
            history['H2_M'].append(obs['H2_M_ratio'])
            history['MFI_inst'].append(obs['MFI_inst'])
            history['MFI_bed'].append(obs['MFI_bed'])
            history['on_spec'].append(self.is_on_spec(obs['MFI_bed']))
            
        return history

    def evaluate_bang_bang(self, t_switch, overshoot_factor, sim_time_min=600.0):
        self.env.reset(self.initial_grade)
        
        overshoot_H2M = self.target_H2M * overshoot_factor
        overshoot_H2M = max(0.01, min(overshoot_H2M, 0.50))
        
        off_spec_time = 0
        for t in range(int(sim_time_min)):
            if t < t_switch:
                setpoint = overshoot_H2M
            else:
                setpoint = self.target_H2M
                
            obs = self.env.step(setpoint)
            if not self.is_on_spec(obs['MFI_bed']):
                off_spec_time += 1
                
        return off_spec_time

    def optimize_bang_bang(self):
        if self.target_MFI > self.initial_MFI:
            overshoot_factor = 1.8
        else:
            overshoot_factor = 0.2
            
        res = minimize_scalar(
            self.evaluate_bang_bang, 
            bounds=(10, 300), 
            args=(overshoot_factor, 600.0), 
            method='bounded'
        )
        
        return self.simulate_bang_bang(res.x, overshoot_factor)

    def simulate_bang_bang(self, t_switch, overshoot_factor, sim_time_min=600.0):
        self.env.reset(self.initial_grade)
        
        overshoot_H2M = self.target_H2M * overshoot_factor
        overshoot_H2M = max(0.01, min(overshoot_H2M, 0.50))
        
        history = {'time': [], 'H2_M': [], 'MFI_inst': [], 'MFI_bed': [], 'on_spec': []}
        
        for t in range(int(sim_time_min)):
            if t < t_switch:
                setpoint = overshoot_H2M
            else:
                setpoint = self.target_H2M
                
            obs = self.env.step(setpoint)
            
            history['time'].append(obs['time'])
            history['H2_M'].append(obs['H2_M_ratio'])
            history['MFI_inst'].append(obs['MFI_inst'])
            history['MFI_bed'].append(obs['MFI_bed'])
            history['on_spec'].append(self.is_on_spec(obs['MFI_bed']))
            
        return history
