CSC 561 Individual Project Proposal 
Project Title 
Comparing Deep Learning Models for Hotel Demand Forecasting and Dynamic Room 
Pricing 
Purpose, Motivation, Impact 
The goal of this project is to build a machine learning system that can forecast hotel room 
demand and generate room pricing recommendations using real historical hotel data. Many 
hotels still rely on manual pricing decisions, spreadsheets, or simple fixed rules, which can be 
slow to update and may not respond well to changing demand. In contrast, modern revenue 
management systems use booking trends, seasonality, room type behavior, and market signals 
to help automate pricing decisions. 
This project is motivated by a real use case involving my dad’s company. If successful, this 
model could help reduce manual pricing work, improve consistency, and potentially save money 
by providing a lower-cost internal alternative to a commercial revenue management platform. 
That gives the project both practical business value and real-world impact. 
From an academic standpoint, this project also fits the course well because it applies deep 
learning to structured sequential data. Instead of treating this as a simple regression problem, I 
want to study how different neural network architectures perform on hotel demand forecasting 
and whether they can support useful pricing recommendations. 
Dataset 
The dataset for this project will come from historical hotel data provided by my dad’s company. 
The expected data include reservations, stay dates, booking dates, room types, rates, 
occupancy, and other operational variables related to pricing decisions. If available, I may also 
include competitor pricing, booking channel, group bookings, event indicators, and other 
market-related signals. 
This dataset is a good fit for the project because it directly captures the relationship between 
hotel demand, pricing, and booking behavior over time. If multiple years of data are available, I 
will use them to capture seasonality, day-of-week effects, holiday effects, and broader demand 
trends. If room-type-specific or segment-specific data are available, those will also be included. 
Methods 
Input Data 
The input data will be structured as tabular time-series data. Each training example will 
represent either a date or a date-room-type combination, with features describing both the 
current business situation and recent historical patterns. Likely features include: 
●  stay date 
●  booking lead time 
●  day of week 
●  month and season 
●  room type 
●  current offered rate 
●  historical occupancy 
●  historical ADR 
●  booking pace 
●  length of stay 
●  group booking indicators 
●  event or holiday indicators 
●  competitor pricing if available 
●  booking channel or market segment if available 
Preprocessing will include handling missing values, encoding categorical variables, normalizing 
numerical features when needed, and creating lagged or rolling-window features to capture 
short-term and medium-term trends. Since this is a time-based forecasting problem, I will use a 
chronological train/validation/test split rather than a random split. Older data will be used for 
training, a middle block for validation, and the most recent block for testing. If enough data are 
available, I may also use rolling-origin evaluation. 
To support deep learning models, the data will also be organized into sequential windows so 
that models can look at multiple past days of booking and pricing behavior before predicting 
future demand. 
Target Variable(s) 
The main target variable will be a future demand-related regression target, such as: 
●  rooms sold for a future stay date 
●  future occupancy percentage 
●  or expected ADR depending on the available data 
The most likely primary target will be future occupancy or rooms sold, since those are directly 
observable and make the forecasting task more straightforward. After demand is predicted, I will 
use that forecast to generate a room pricing recommendation within a realistic range of 
business constraints. 
I may also include a secondary classification task, such as predicting whether a given date falls 
into a high-demand period. 
Model 
To better align this project with CSC 561, I plan to compare both classical machine learning 
baselines and deep learning models. 
Baselines 
●  simple heuristic baseline such as moving average or last-year-same-day demand 
●  linear regression 
●  XGBoost or Random Forest for tabular forecasting 
Deep Learning Models 
●  Multilayer Perceptron (MLP): a basic feedforward neural network for structured feature 
prediction 
●  LSTM: to model booking pace and historical occupancy as a sequence over time 
●  GRU: a lighter recurrent alternative to LSTM for time-series forecasting 
●  Transformer-based time-series model: a small Transformer encoder to capture 
longer-range temporal relationships in booking behavior and demand patterns 
The main technical focus of the project is comparing deep learning architectures for hotel 
demand forecasting using real operational time-series data, while including classical machine 
learning approaches as baselines. 
The overall MVP will likely use a two-stage pipeline: 
1.  Forecast future demand using one of the candidate models 
2.  Convert that demand forecast into a room pricing recommendation using a bounded 
pricing rule or simple optimization layer 
This project is not meant to recreate a full commercial revenue management system. The goal 
is to build a realistic academic MVP that focuses on the core problem of demand forecasting 
and pricing support. 
Metrics and Results 
The project will be evaluated using both predictive metrics and business-oriented metrics. 
For forecasting performance, I plan to report: 
●  MAE 
●  RMSE 
●  MAPE 
●  R² 
If I include a classification subtask, I may also report: 
●  accuracy 
●  precision 
●  recall 
●  F1 score 
●  AUROC 
For business impact, I will compare: 
●  historical or manual pricing performance 
●  simulated revenue under model-assisted pricing 
●  occupancy differences 
●  ADR differences 
●  RevPAR differences 
Results will be shown using: 
●  prediction vs. actual plots for occupancy or demand 
●  time-series plots of recommended price versus actual price 
●  feature importance or attribution plots 
●  comparison tables between baselines and deep learning models 
●  an architecture diagram of the final pipeline 
●  scenario examples for high-demand weekends, holidays, or local events  
If enough data are available, I will also test the model on a held-out later time period to evaluate 
how well it generalizes to new booking conditions. 
Overlap Statement 
This project is not intended to overlap with another course project. It is based on a real-world 
hotel pricing and demand forecasting problem connected to my dad’s company, but the model 
design, implementation, evaluation, and final report will all be completed specifically for CSC 
561.