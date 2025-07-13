import streamlit as st
import pandas as pd


st.title("Transaction Details")
df = pd.read_csv("D:\\myWealthcomAPI\\backend\\uploads\\output.csv")
df.columns = df.columns.str.strip()
for col in ['Debit', 'Credit', 'Balance']:
    df[col] = (
        df[col]
        .astype(str)
        .str.replace(',', '', regex=False)
        .str.strip()
    )
    df[col] = pd.to_numeric(df[col], errors='coerce')

# Clean Name column
df['names'] = df['names'].astype(str).str.strip()

df1 = df.drop(columns=['Description','Value Date','Ref No./Cheque No.'])
st.header("All Transactions:")
st.write(df1)

df1['Debit'] = pd.to_numeric(df['Debit'], errors='coerce')
df1.dropna(subset=['Debit'])

topdebit=df1
topdebit=topdebit.drop(columns=['Credit','Unnamed: 7','Balance'])
st.header("Top 5 Debit:")
st.write(topdebit.nlargest(5,'Debit'))

df = df.dropna(subset=['names', 'Debit'])

grouped_df = df.groupby('names', as_index=False)['Debit'].sum()
grouped_df = grouped_df.sort_values(by='Debit', ascending=False)
st.header("Places or people I spent/lent most money:")
st.dataframe(grouped_df)
