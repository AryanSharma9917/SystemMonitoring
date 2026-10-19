import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity

path = "data/"

df = pd.read_csv(path+'OnlineRetail.csv', dtype={
                 'CustomerID': str, 'InvoiceID': str}, encoding='unicode_escape')

df = df.loc[df['Quantity'] > 0]
df = df.dropna(subset=['CustomerID']).reset_index(drop=True)

customer_item_matrix = df.pivot_table(
    index='CustomerID',
    columns='StockCode',
    values='Quantity',
    aggfunc='sum')

customer_item_matrix = customer_item_matrix.applymap(
    lambda x: 1 if x > 0 else 0)

user_user_sim_matrix = pd.DataFrame(cosine_similarity(customer_item_matrix))
user_user_sim_matrix.columns = customer_item_matrix.index
user_user_sim_matrix['CustomerID'] = customer_item_matrix.index
user_user_sim_matrix = user_user_sim_matrix.set_index('CustomerID')

item_item_sim_matrix = pd.DataFrame(cosine_similarity(customer_item_matrix.T))
item_item_sim_matrix.columns = customer_item_matrix.T.index
item_item_sim_matrix['StockCode'] = customer_item_matrix.T.index
item_item_sim_matrix = item_item_sim_matrix.set_index('StockCode')

user_user_sim_matrix.to_pickle(path+'user_user_sim_matrix.p')
item_item_sim_matrix.to_pickle(path+'item_item_sim_matrix.p')
customer_item_matrix.to_pickle(path+'customer_item_matrix.p')
df.to_pickle(path+'df.p')
