from brix import Handler
from indicators import Giants

table_name = 'minerva'
H = Handler(table_name,quietly=False)
giants = Giants(quietly=False,color_method='quantile')
H.add_indicator(giants)
H.listen()
