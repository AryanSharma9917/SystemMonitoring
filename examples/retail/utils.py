def most_similar_user_finder(df, id):
    similar_user = df.loc[id].sort_values(
        ascending=False).index[1]
    return similar_user


def bought_by_x(df, id):
    items_bought_by_x = set(df.loc[id].loc[df.loc[id] > 0].index)
    return items_bought_by_x


def recommended_items(transaction_df, items_to_recommend, n=5):
    return transaction_df.loc[transaction_df['StockCode'].isin(items_to_recommend), ['StockCode', 'Description']].drop_duplicates()['StockCode'].head(n).tolist()


def recommend_customer(user_df, item_df, transaction_df, user_id, n=5):
    print('Recommendations for user:', user_id)
    user = most_similar_user_finder(user_df, user_id)
    print('Most similar user:', user)
    items_bought_by_a = bought_by_x(item_df, user_id)
    items_bought_by_b = bought_by_x(item_df, user)
    print('Items bought by user %s:' % user_id, len(items_bought_by_a))
    print('Items bought by user %s:' % user, len(items_bought_by_b))
    items_to_recommend = items_bought_by_a - items_bought_by_b
    return recommended_items(transaction_df, items_to_recommend, n)


def get_similar_items(item_df, item_id, n=5):
    similar_items = item_df.loc[item_id].sort_values(
        ascending=False).index[1:n].tolist()
    return similar_items
