import torch
import torch.nn as nn
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from reactor_simulator import PolyolefinReactor

class LSTMSoftSensor(nn.Module):
    def __init__(self, input_size=4, hidden_size=32, num_layers=1, output_size=1):
        super(LSTMSoftSensor, self).__init__()
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True)
        self.fc = nn.Linear(hidden_size, output_size)
        
    def forward(self, x):
        h0 = torch.zeros(self.num_layers, x.size(0), self.hidden_size).to(x.device)
        c0 = torch.zeros(self.num_layers, x.size(0), self.hidden_size).to(x.device)
        out, _ = self.lstm(x, (h0, c0))
        out = self.fc(out[:, -1, :])
        return out

class SoftSensorManager:
    def __init__(self, sequence_length=30):
        self.model = LSTMSoftSensor()
        self.seq_len = sequence_length
        self.scaler_X = StandardScaler()
        self.scaler_y = StandardScaler()
        self.is_trained = False
        
    def generate_dummy_training_data(self):
        env = PolyolefinReactor()
        data = []
        env.reset('A')
        setpoint = 0.05
        
        for t in range(2000):
            if t % 60 == 0:
                setpoint = np.random.uniform(0.02, 0.40)
            
            obs = env.step(setpoint)
            data.append([
                obs['H2_M_ratio'], 
                obs['T_bed'], 
                obs['production_rate'], 
                100.0 + np.random.normal(0,1),
                obs['MFI_bed']
            ])
            
        df = pd.DataFrame(data, columns=['H2_M', 'T_bed', 'Prod_Rate', 'Pressure', 'MFI_bed'])
        return df

    def train(self):
        df = self.generate_dummy_training_data()
        X = df[['H2_M', 'T_bed', 'Prod_Rate', 'Pressure']].values
        y = df[['MFI_bed']].values
        
        X_scaled = self.scaler_X.fit_transform(X)
        y_scaled = self.scaler_y.fit_transform(y)
        
        X_seq, y_seq = [], []
        for i in range(len(X_scaled) - self.seq_len):
            X_seq.append(X_scaled[i:i+self.seq_len])
            y_seq.append(y_scaled[i+self.seq_len])
            
        X_tensor = torch.FloatTensor(np.array(X_seq))
        y_tensor = torch.FloatTensor(np.array(y_seq))
        
        criterion = nn.MSELoss()
        optimizer = torch.optim.Adam(self.model.parameters(), lr=0.01)
        
        self.model.train()
        for epoch in range(10): 
            optimizer.zero_grad()
            outputs = self.model(X_tensor)
            loss = criterion(outputs, y_tensor)
            loss.backward()
            optimizer.step()
            
        self.is_trained = True

    def predict(self, history_df):
        if not self.is_trained:
            self.train()
            
        self.model.eval()
        X = history_df[['H2_M', 'T_bed', 'Prod_Rate', 'Pressure']].values
        X_scaled = self.scaler_X.transform(X)
        X_tensor = torch.FloatTensor(X_scaled).unsqueeze(0)
        
        with torch.no_grad():
            y_scaled = self.model(X_tensor).numpy()
            
        y_pred = self.scaler_y.inverse_transform(y_scaled)
        return y_pred[0][0]
