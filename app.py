"""
CS 230 Final Project
Name: Adrian Suero
Section: CS230-7
Dataset: Global Power Plants 
App URL: https://adrian-cs230-project-83z5abehd7fhwt4ajedp5j.streamlit.app/
Description: Power Plant Deal Screener. Built for an investment banking
             analyst screening M&A and project-finance targets. It compares
             fuel mix by country, maps large plants of a chosen fuel, and
             lists the largest plants for a target list.
LLM(s) used: Claude
"""

import pandas as pd
import plotly.express as px
import pydeck as pdk
import streamlit as st

DATA_FILE = "power_plants_6_countries.csv"  # relative path so it runs anywhere

REQUIRED_COLUMNS = ["name", "country_long", "primary_fuel",
                    "capacity_mw", "latitude", "longitude"]

#[DICT_DRIVEN] AUGMENT - added FUEL_LABELS for the Q1 legend and Q2/Q3 dropdowns; removed Petcoke from FUEL_COLORS.
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
    "Other": "#c7c7c7",
}

FUEL_LABELS = {
    "Solar": "Solar",
    "Wind": "Wind",
    "Hydro": "Hydro",
    "Coal": "Coal",
    "Gas": "Gas",
    "Oil": "Oil",
    "Nuclear": "Nuclear",
    "Biomass": "Biomass",
    "Waste": "Waste",
    "Geothermal": "Geothermal",
    "Wave And Tidal": "Wave and tidal",
    "Cogeneration": "Cogeneration",
    "Storage": "Storage",
    "Other": "Other",
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


#[REUSE_FUNC] IDENTIFY & EXPLAIN - filters by country, fuel, and minimum MW for all three pages.
# Sharing one function keeps the screening rules consistent across Q1, Q2, and Q3.
# Example: Canada, Hydro, and min_mw=1000 returns a DataFrame of 20 plants;
# its largest is Robert-Bourassa at 5,616 MW.
def filter_plants(df, countries, fuel="All", min_mw=0):
    """Return plants in the chosen countries, optionally by fuel and size."""
    result = df[df["country_long"].isin(countries)]
    if fuel != "All":
        result = result[result["primary_fuel"] == fuel]
    result = result[result["capacity_mw"] >= min_mw]
    return result


#[AI_REWRITE] REVISE / REWRITE - totals each country's fuels in a loop, then calculates each share.
def fuel_mix(df):
    # Add capacity for each country and fuel to one grouped row.
    totals = df.groupby(["country_long", "primary_fuel"])["capacity_mw"].sum().reset_index()
    # Start a lookup for each country's full generating capacity.
    country_totals = {}
    # Visit each grouped country-and-fuel row.
    for _, row in totals.iterrows():
        # Get the country for this fuel row.
        country = row["country_long"]
        # Add this fuel's capacity to that country's running total.
        country_totals[country] = country_totals.get(country, 0) + row["capacity_mw"]
    # Start a list for each fuel's percentage of its country's capacity.
    shares = []
    # Visit each grouped row again to calculate its percentage.
    for _, row in totals.iterrows():
        # Look up the full capacity for this row's country.
        country_total = country_totals[row["country_long"]]
        # Divide this fuel's capacity by the country total and convert to percent.
        share = row["capacity_mw"] / country_total * 100
        # Save the calculated percentage in row order.
        shares.append(share)
    # Add the calculated percentages to the grouped table.
    totals["share_pct"] = shares
    # Return grouped capacity and its percentage for the chart.
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

    # Stop when no country is selected so the fuel-mix chart has data to show.
    if not chosen:
        st.warning("Select at least one country to see the fuel mix.")
        return

    subset = filter_plants(plants, chosen)
    mix = fuel_mix(subset)
    # Add the readable fuel names used in the chart legend.
    mix["fuel_label"] = mix["primary_fuel"].map(FUEL_LABELS).fillna(mix["primary_fuel"])

    fig = px.bar(
        mix, x="country_long", y="share_pct", color="fuel_label",
        color_discrete_map={FUEL_LABELS.get(fuel, fuel): color
                            for fuel, color in FUEL_COLORS.items()},
        title="Share of Total Generating Capacity by Fuel",
        labels={"country_long": "Country",
                "share_pct": "Share of capacity (%)",
                "fuel_label": "Fuel"},
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

    # Stop here if the dataset has no plants.
    if plants.empty:
        st.info("No plants are available to map.")
        return

    country = st.selectbox("Country", sorted(plants["country_long"].unique()))
    fuels_here = sorted(plants[plants["country_long"] == country]["primary_fuel"].unique())
    fuel = st.selectbox("Fuel", fuels_here,
                        format_func=lambda value: FUEL_LABELS.get(value, value))
    min_mw = st.slider("Minimum capacity (MW)", 0, 10000, 100, step=10)

    matches = filter_plants(plants, [country], fuel, min_mw)

    #[INPUT_CHECK] AUGMENT - show the largest available plant when the chosen minimum is too high.
    if matches.empty:
        candidates = filter_plants(plants, [country], fuel)
        largest = candidates.nlargest(1, "capacity_mw").iloc[0]
        st.info(f"No {fuel} plants in {country} have at least {min_mw} MW. "
                f"The largest is {largest['name']} at "
                f"{largest['capacity_mw']:,.0f} MW. Try lowering the minimum.")
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

    fuel = st.selectbox(
        "Fuel", all_fuels,
        index=all_fuels.index("Hydro") if "Hydro" in all_fuels else 0,
        format_func=lambda value: FUEL_LABELS.get(value, value),
    )
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
#[DEPLOY] IDENTIFY & EXPLAIN - the Streamlit Community Cloud app URL is documented in the project header.
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
