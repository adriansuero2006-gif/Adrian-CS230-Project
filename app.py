"""
CS 230 Final Project
Name: Adrian Suero
Section: CS230-7
Dataset: Global Power Plants (6 countries), World Resources Institute
          Global Power Plant Database (CC BY 4.0)
App URL: (add after deploying to Streamlit Community Cloud)
Description: Power Plant Deal Screener. Built for an investment banking
             analyst screening M&A and project-finance targets. It compares
             fuel mix by country, maps large plants of a chosen fuel, and
             lists the largest plants for a target list.
LLM(s) used: (fill in)
References: (fill in)
"""

import pandas as pd
import plotly.express as px
import pydeck as pdk
import streamlit as st

DATA_FILE = "power_plants_6_countries.csv"  # relative path so it runs anywhere

REQUIRED_COLUMNS = ["name", "country_long", "primary_fuel",
                    "capacity_mw", "latitude", "longitude"]

# Chart and map color for each fuel (keys match the cleaned primary_fuel text).
FUEL_COLORS = {
    "Solar": "#f4c542",
    "Wind": "#5bc0de",
    "Hydro": "#1f77b4",
    "Coal": "#4d4d4d",
    "Gas": "#ff7f0e",
    "Oil": "#8c564b",
    "Nuclear": "#9467bd",
    "Biomass": "#2ca02c",
    "Waste": "#bcbd22",
    "Geothermal": "#d62728",
    "Wave And Tidal": "#17becf",
    "Cogeneration": "#e377c2",
    "Storage": "#7f7f7f",
    "Petcoke": "#393b79",
    "Other": "#c7c7c7",
}


# ------------------------------------------------------------ data
@st.cache_data
def load_data(path):
    """Read the CSV and clean it. Returns a DataFrame."""
    df = pd.read_csv(path)

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"The CSV is missing these columns: {missing}")

    # Clean the text columns: remove extra spaces and fix capitalization.
    df["name"] = df["name"].astype(str).str.strip()
    df["country_long"] = df["country_long"].astype(str).str.strip()
    df["primary_fuel"] = df["primary_fuel"].astype(str).str.strip().str.title()

    # Force the number columns to numbers; bad values become NaN.
    for col in ["capacity_mw", "latitude", "longitude"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Drop rows we cannot use: no capacity, no fuel, or no location.
    df = df.dropna(subset=["capacity_mw", "primary_fuel",
                           "latitude", "longitude"])
    df = df[df["capacity_mw"] > 0]

    return df.reset_index(drop=True)


def filter_plants(df, countries, fuel="All", min_mw=0):
    """Return plants in the chosen countries, optionally by fuel and size."""
    result = df[df["country_long"].isin(countries)]
    if fuel != "All":
        result = result[result["primary_fuel"] == fuel]
    result = result[result["capacity_mw"] >= min_mw]
    return result


def fuel_mix(df):
    """Percent of each country's total capacity from each fuel."""
    totals = df.groupby(["country_long", "primary_fuel"])["capacity_mw"].sum()
    totals = totals.reset_index()
    country_total = totals.groupby("country_long")["capacity_mw"].transform("sum")
    totals["share_pct"] = totals["capacity_mw"] / country_total * 100
    return totals


def hex_to_rgb(hex_color):
    """Turn '#1f77b4' into [31, 119, 180] (the format PyDeck wants)."""
    return [int(hex_color[i:i + 2], 16) for i in (1, 3, 5)]


# ------------------------------------------------------------ pages
def page_fuel_mix(plants):
    st.header("Q1: How does the fuel mix compare between countries?")
    st.write("Pick countries to see what share of each country's total "
             "generating capacity comes from each fuel.")

    all_countries = sorted(plants["country_long"].unique())
    chosen = st.multiselect("Countries", all_countries,
                            default=all_countries[:2])

    if not chosen:
        st.warning("Select at least one country to see the fuel mix.")
        return

    subset = filter_plants(plants, chosen)
    mix = fuel_mix(subset)

    fig = px.bar(
        mix, x="country_long", y="share_pct", color="primary_fuel",
        color_discrete_map=FUEL_COLORS,
        title="Share of Total Generating Capacity by Fuel",
        labels={"country_long": "Country",
                "share_pct": "Share of capacity (%)",
                "primary_fuel": "Fuel"},
    )
    fig.update_layout(barmode="stack", yaxis_range=[0, 100],
                      legend_title_text="Fuel")
    st.plotly_chart(fig)

    st.caption("Shares use total capacity (MW), not plant counts. Counting "
               "plants would exaggerate solar, because there are many small "
               "solar sites. Capacity is the plant's rated maximum output, "
               "not what it actually generated.")


def page_map(plants):
    st.header("Q2: Where are the large plants of a fuel in a country?")
    st.write("Choose a country, a fuel, and a minimum size. Bigger dots are "
             "bigger plants.")

    country = st.selectbox("Country", sorted(plants["country_long"].unique()))
    fuels_here = sorted(plants[plants["country_long"] == country]["primary_fuel"].unique())
    fuel = st.selectbox("Fuel", fuels_here)
    min_mw = st.slider("Minimum capacity (MW)", 0, 10000, 100, step=10)

    matches = filter_plants(plants, [country], fuel, min_mw)

    if matches.empty:
        st.info(f"No {fuel} plants in {country} have at least {min_mw} MW. "
                "Try lowering the minimum.")
        return

    st.write(f"Showing **{len(matches)}** plants, "
             f"**{matches['capacity_mw'].sum():,.0f} MW** in total.")

    # Map columns: dot size grows with capacity, dot color comes from the fuel.
    matches = matches.copy()
    matches["radius"] = matches["capacity_mw"] ** 0.5 * 100
    matches["color"] = [hex_to_rgb(FUEL_COLORS.get(f, "#999999"))
                        for f in matches["primary_fuel"]]

    # Zoom out for countries whose plants are spread over a large area.
    spread = max(matches["latitude"].max() - matches["latitude"].min(),
                 matches["longitude"].max() - matches["longitude"].min())
    if spread > 20:
        zoom = 3
    elif spread > 10:
        zoom = 4
    else:
        zoom = 5

    layer = pdk.Layer(
        "ScatterplotLayer",
        data=matches,
        get_position="[longitude, latitude]",
        get_radius="radius",
        get_fill_color="color",
        radius_min_pixels=3,
        radius_max_pixels=40,
        pickable=True,
        opacity=0.7,
    )
    view = pdk.ViewState(latitude=matches["latitude"].mean(),
                         longitude=matches["longitude"].mean(),
                         zoom=zoom)
    tooltip = {"html": "<b>{name}</b><br/>{primary_fuel}<br/>"
                       "{capacity_mw} MW"}
    st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view,
                             tooltip=tooltip, map_style="light"))

    st.caption("Hover over a dot for the plant name and capacity. Some "
               "plants may share a location, so dots can overlap.")


def page_top_plants(plants):
    st.header("Q3: What are the largest plants of a fuel?")
    st.write("Build a quick target list: the biggest plants of one fuel "
             "across the countries you choose.")

    all_countries = sorted(plants["country_long"].unique())
    all_fuels = sorted(plants["primary_fuel"].unique())

    fuel = st.selectbox("Fuel", all_fuels,
                        index=all_fuels.index("Hydro") if "Hydro" in all_fuels else 0)
    n = st.slider("Number of plants (N)", 5, 50, 10)
    chosen = st.multiselect("Countries", all_countries, default=all_countries)

    if not chosen:
        st.warning("Select at least one country.")
        return

    matches = filter_plants(plants, chosen, fuel)
    if matches.empty:
        st.info(f"No {fuel} plants found in the selected countries.")
        return

    top = matches.sort_values("capacity_mw", ascending=False).head(n)
    if len(top) < n:
        st.info(f"Only {len(top)} {fuel} plants match, so that is all "
                "that is shown.")

    # Chart label combines name, country, and size so plants that share a
    # name (the data has two "Dinorwig" records) get separate bars.
    top = top.copy()
    top["label"] = (top["name"] + " (" + top["country_long"] + ", "
                    + top["capacity_mw"].round(0).astype(int).astype(str) + " MW)")

    fig = px.bar(
        top, x="capacity_mw", y="label", color="country_long",
        orientation="h",
        title=f"Top {len(top)} {fuel} Plants by Capacity",
        labels={"capacity_mw": "Capacity (MW)", "label": "Plant",
                "country_long": "Country"},
    )
    fig.update_layout(yaxis={"categoryorder": "total ascending"},
                      legend_title_text="Country")
    st.plotly_chart(fig)

    table = top[["name", "country_long", "primary_fuel", "capacity_mw"]]
    table = table.rename(columns={"name": "Plant", "country_long": "Country",
                                  "primary_fuel": "Fuel",
                                  "capacity_mw": "Capacity (MW)"})
    st.dataframe(table, hide_index=True)

    st.caption("Capacity is rated output in megawatts. A large plant is not "
               "necessarily a good deal: ownership and age are not in this "
               "dataset.")


# ------------------------------------------------------------ app
st.set_page_config(page_title="Power Plant Deal Screener", layout="wide")
st.title("Power Plant Deal Screener")
st.write("A screening tool for power and energy deal teams, using the World "
         "Resources Institute Global Power Plant Database (UK, Brazil, "
         "France, India, Germany, Canada).")

try:
    plants = load_data(DATA_FILE)
except FileNotFoundError:
    st.error(f"Could not find {DATA_FILE}. Put it in the same folder as "
             "app.py.")
    st.stop()
except ValueError as err:
    st.error(str(err))
    st.stop()

st.sidebar.header("Navigate")
page = st.sidebar.radio("Choose a question", [
    "Q1: Fuel mix by country",
    "Q2: Map of large plants",
    "Q3: Largest plants list",
])

if page.startswith("Q1"):
    page_fuel_mix(plants)
elif page.startswith("Q2"):
    page_map(plants)
else:
    page_top_plants(plants)
