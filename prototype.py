from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Set, Tuple
import math
from pathlib import Path
import streamlit as st

@dataclass
class SprintPlanningInstance:
    S: List[int]                      # sprints
    U: List[int]                      # stories
    U_star: Set[int]                  # critical stories

    u: Dict[int, int]                 # business utility
    p: Dict[int, int]                 # story points
    r_cr: Dict[int, float]            # criticality multiplier
    r_un: Dict[int, float]            # uncertainty multiplier

    p_max: Dict[int, int]             # sprint capacities
    F: int                            # sprint activation penalty

    U_AND: Set[int]
    U_OR: Set[int]
    D_AND: Dict[int, Set[int]]
    D_OR: Dict[int, Set[int]]

    A: Dict[Tuple[int, int], int]     # affinity gains for (k,l), k<l

    d: float

def load_instance_from_aspp(filepath):
    """
    Read a SprintPlanningInstance from an ASPP text file.
    """
    filepath = Path(filepath)

    with open(filepath, "r", encoding="utf-8") as f:
        raw_lines = [line.strip() for line in f if line.strip()]

    name = None
    S, U, U_star = [], [], set()
    p_max = {}
    u, p, r_cr, r_un = {}, {}, {}, {}
    U_AND, U_OR = set(), set()
    D_AND, D_OR = {}, {}
    A = {}
    F = None
    d = None

    section = None

    for line in raw_lines:
        if line.startswith("#"):
            continue

        if line.startswith("NAME:"):
            name = line.split(":", 1)[1].strip()
            continue
        if line.startswith("N_STORIES:"):
            continue
        if line.startswith("N_SPRINTS:"):
            continue
        if line.startswith("F:"):
            F = int(line.split(":", 1)[1].strip())
            continue
        if line.startswith('d:'):
            d = float(line.split(":", 1)[1].strip())
            continue
        if line.startswith("S:"):
            S = list(map(int, line.split(":", 1)[1].split()))
            continue
        if line.startswith("U:"):
            U = list(map(int, line.split(":", 1)[1].split()))
            continue
        if line.startswith("U_STAR:"):
            rhs = line.split(":", 1)[1].strip()
            U_star = set(map(int, rhs.split())) if rhs else set()
            continue
        if line == "P_MAX:":
            section = "P_MAX"
            continue
        if line == "STORY_DATA:":
            section = "STORY_DATA"
            continue
        if line.startswith("U_AND:"):
            rhs = line.split(":", 1)[1].strip()
            U_AND = set(map(int, rhs.split())) if rhs else set()
            continue
        if line == "D_AND:":
            section = "D_AND"
            continue
        if line.startswith("U_OR:"):
            rhs = line.split(":", 1)[1].strip()
            U_OR = set(map(int, rhs.split())) if rhs else set()
            continue
        if line == "D_OR:":
            section = "D_OR"
            continue
        if line == "AFFINITIES:":
            section = "AFFINITIES"
            continue

        # Parse section content
        if section == "P_MAX":
            i, cap = line.split()
            p_max[int(i)] = int(cap)

        elif section == "STORY_DATA":
            j, uj, pj, rcrj, runj = line.split()
            j = int(j)
            u[j] = int(uj)
            p[j] = int(pj)
            r_cr[j] = float(rcrj)
            r_un[j] = float(runj)

        elif section == "D_AND":
            if ":" in line:
                lhs, rhs = line.split(":", 1)
                j = int(lhs.strip())
                preds = rhs.strip()
                D_AND[j] = set(map(int, preds.split())) if preds else set()

        elif section == "D_OR":
            if ":" in line:
                lhs, rhs = line.split(":", 1)
                j = int(lhs.strip())
                preds = rhs.strip()
                D_OR[j] = set(map(int, preds.split())) if preds else set()

        elif section == "AFFINITIES":
            k, l, val = line.split()
            A[(int(k), int(l))] = int(val)

    inst = SprintPlanningInstance(
        S=S,
        U=U,
        U_star=U_star,
        u=u,
        p=p,
        r_cr=r_cr,
        r_un=r_un,
        p_max=p_max,
        F=F,
        U_AND=U_AND,
        U_OR=U_OR,
        D_AND=D_AND,
        D_OR=D_OR,
        A=A,
        d = d
    )

    return inst

def print_instance_summary(inst: SprintPlanningInstance) -> None:
    print("Sprints:", inst.S)
    print("Stories:", inst.U)
    print("Critical stories U*:", sorted(inst.U_star))
    print("Sprint capacities p_max:", inst.p_max)
    print("Sprint penalty F:", inst.F)
    print("Discount rate d:", inst.d)
    print()

    print("Story parameters:")
    for j in inst.U:
        print(
            f"j={j:>2} | p={inst.p[j]:>2} | u={inst.u[j]:>2} | "
            f"r_cr={inst.r_cr[j]:.2f} | r_un={inst.r_un[j]:.2f}"
        )

    print()
    print("AND dependencies:")
    for j in sorted(inst.U_AND):
        print(f"  {j} <- {sorted(inst.D_AND[j])}")

    print("OR dependencies:")
    for j in sorted(inst.U_OR):
        print(f"  {j} <- one of {sorted(inst.D_OR[j])}")

    print("Affinities:")
    for (k, l), val in sorted(inst.A.items()):
        print(f"  A[{k},{l}] = {val}")


def parse_story_input(text):
    """
    Parse a text input like:
        "1, 4, 7 9"
    into a list of distinct integers.

    Accepts commas and/or spaces.
    Empty input -> []
    """
    text = text.strip()
    if not text:
        return []

    tokens = text.replace(",", " ").split()
    stories = [int(tok) for tok in tokens]
    return stories


def build_solution_dict_from_sprints(sprint_to_stories):
    """
    Convert:
        {1: [9,14], 2: [11,21], ...}
    into:
        {9:1, 14:1, 11:2, 21:2, ...}

    Also detects duplicates across sprints.
    """
    solution_dict = {}
    errors = []

    for i, stories in sprint_to_stories.items():
        for j in stories:
            if j in solution_dict:
                errors.append(
                    f"Story {j} appears more than once "
                    f"(already assigned to sprint {solution_dict[j]}, also entered in sprint {i})."
                )
            else:
                solution_dict[j] = i

    return solution_dict, errors


def validate_solution(inst, solution_dict, tol=1e-9):
    """
    Validate:
    1. Story/sprint IDs are valid
    2. Capacity constraints
    3. All critical stories are selected
    4. AND precedence constraints
    5. OR precedence constraints
    """
    errors = []

    S = set(inst.S)
    U = set(inst.U)
    U_star = set(inst.U_star)

    # Basic ID checks
    for j, i in solution_dict.items():
        if j not in U:
            errors.append(f"Story {j} is not a valid story.")
        if i not in S:
            errors.append(f"Story {j} is assigned to invalid sprint {i}.")

    sol = {j: i for j, i in solution_dict.items() if j in U and i in S}

    # Capacity
    sprint_loads = {i: 0.0 for i in inst.S}
    for j, i in sol.items():
        sprint_loads[i] += inst.p[j] * inst.r_un[j]

    for i in inst.S:
        if sprint_loads[i] > inst.p_max[i] + tol:
            errors.append(
                f"Capacity violated in sprint {i}: "
                f"load = {sprint_loads[i]:.2f}, capacity = {inst.p_max[i]:.2f}"
            )

    # Critical stories
    selected_stories = set(sol.keys())
    missing_critical = sorted(U_star - selected_stories)
    if missing_critical:
        errors.append(f"Missing critical stories: {missing_critical}")

    # AND precedence
    for j in inst.U_AND:
        if j in sol:
            sprint_j = sol[j]
            preds = inst.D_AND[j]

            missing_preds = [z for z in preds if z not in sol]
            late_preds = [z for z in preds if z in sol and sol[z] > sprint_j]

            if missing_preds:
                errors.append(
                    f"AND precedence violated for story {j}: "
                    f"missing predecessors {sorted(missing_preds)}"
                )
            if late_preds:
                errors.append(
                    f"AND precedence violated for story {j}: "
                    f"predecessors scheduled after story {j}: {sorted(late_preds)}"
                )

    # OR precedence
    for j in inst.U_OR:
        if j in sol:
            sprint_j = sol[j]
            preds = inst.D_OR[j]
            feasible_preds = [z for z in preds if z in sol and sol[z] <= sprint_j]

            if len(feasible_preds) == 0:
                errors.append(
                    f"OR precedence violated for story {j}: "
                    f"none of {sorted(preds)} is scheduled in sprint <= {sprint_j}"
                )

    return {
        "is_valid": len(errors) == 0,
        "errors": errors,
        "sprint_loads": sprint_loads,
    }


def compute_objective(inst, solution_dict, d):
    """
    Compute the discounted objective:

    sum_i exp(-d(i-1)) [
        sum_j u_j r_cr_j x_ij
        + sum_{k<l} A_kl x_ik x_il
        - F y_i
    ]

    Here solution_dict is {story: sprint}.
    """
    sprint_to_stories = {i: [] for i in inst.S}
    for j, i in solution_dict.items():
        if i in sprint_to_stories:
            sprint_to_stories[i].append(j)

    total = 0.0
    details = {}

    for i in inst.S:
        stories_i = sprint_to_stories[i]
        y_i = 1 if len(stories_i) > 0 else 0
        discount_i = math.exp(-d * (i - 1))

        story_term = sum(inst.u[j] * inst.r_cr[j] for j in stories_i)

        affinity_term = 0.0
        stories_set = set(stories_i)
        for (k, l), val in inst.A.items():
            if k in stories_set and l in stories_set:
                affinity_term += val

        penalty_term = inst.F * y_i

        sprint_value = discount_i * (story_term + affinity_term - penalty_term)
        total += sprint_value

        details[i] = {
            "discount": discount_i,
            "story_term": story_term,
            "affinity_term": affinity_term,
            "penalty_term": penalty_term,
            "total_contribution": sprint_value,
        }

    return total, details

# ============================================================
# Load Data
# ============================================================

inst = load_instance_from_aspp("instance_001.aspp")
# print_instance_summary(inst)


# ============================================================
# Streamlit UI
# ============================================================
st.set_page_config(page_title="Agile Sprint Planning Checker", layout="wide")

st.title("Agile Sprint Planning Prototype")
st.write(
    "Enter the story IDs assigned to each sprint. "
    "Use commas or spaces, for example: `1, 4, 7 9`."
)

with st.expander("Instance summary", expanded=False):
    st.write(f"Stories: {len(inst.U)}")
    st.write(f"Sprints: {list(inst.S)}")
    st.write(f"Critical stories: {sorted(inst.U_star)}")
    st.write(f"Sprint capacities: {inst.p_max}")
    st.write(f"Fixed sprint penalty F: {inst.F}")

st.subheader("Sprint inputs")

def reset_form():
    for key in ["s1", "s2", "s3", "s4", "s5", "s6"]:
        st.session_state[key] = ""

# Initialize session state for text boxes
for key in ["s1", "s2", "s3", "s4", "s5", "s6"]:
    if key not in st.session_state:
        st.session_state[key] = ""

col1, col2 = st.columns(2)

with col1:
    sprint_1_text = st.text_area("Sprint 1", height=80, key="s1")
    sprint_2_text = st.text_area("Sprint 2", height=80, key="s2")
    sprint_3_text = st.text_area("Sprint 3", height=80, key="s3")

with col2:
    sprint_4_text = st.text_area("Sprint 4", height=80, key="s4")
    sprint_5_text = st.text_area("Sprint 5", height=80, key="s5")
    sprint_6_text = st.text_area("Sprint 6", height=80, key="s6")



# d = st.number_input(
#     "Discount rate d",
#     min_value=0.0,
#     value=0.20,
#     step=0.01,
#     format="%.2f"
# )

d = inst.d

button_col1, button_col2 = st.columns([1, 1])

with button_col1:
    submit = st.button("Submit plan", type="primary")

with button_col2:
    reset = st.button("Reset", on_click=reset_form)


if submit:
    parsing_errors = []
    sprint_to_stories = {}

    raw_inputs = {
        1: sprint_1_text,
        2: sprint_2_text,
        3: sprint_3_text,
        4: sprint_4_text,
        5: sprint_5_text,
        6: sprint_6_text,
    }

    # Parse each sprint input
    for i, txt in raw_inputs.items():
        try:
            sprint_to_stories[i] = parse_story_input(txt)
        except ValueError:
            parsing_errors.append(
                f"Sprint {i} contains invalid input. "
                f"Please use only integers separated by commas or spaces."
            )

    if parsing_errors:
        st.error("Input parsing failed.")
        for err in parsing_errors:
            st.write(f"- {err}")
    else:
        # Build solution dictionary and check duplicates across sprints
        solution_dict, duplicate_errors = build_solution_dict_from_sprints(sprint_to_stories)

        # Validate
        validation = validate_solution(inst, solution_dict)

        all_errors = duplicate_errors + validation["errors"]

        ## Display solution dictionary
        # st.subheader("Interpreted solution")
        # st.json(solution_dict)

        # Capacity report
        st.subheader("Sprint loads")
        load_rows = []
        for i in inst.S:
            load_rows.append({
                "Sprint": i,
                "Load": round(validation["sprint_loads"][i], 2),
                "Capacity": round(inst.p_max[i], 2),
                "Feasible": validation["sprint_loads"][i] <= inst.p_max[i] + 1e-9,
            })
        st.dataframe(load_rows, use_container_width=True)

        # Validation outcome
        st.subheader("Constraint verification")
        if len(all_errors) == 0:
            st.success("The plan is feasible with respect to capacities, critical stories, and precedence constraints.")
        else:
            st.error("The plan violates one or more constraints.")
            for err in all_errors:
                st.write(f"- {err}")

        # Objective value
        obj_value, obj_details = compute_objective(inst, solution_dict, d)

        st.subheader("Objective value")
        st.metric("Objective", f"{obj_value:.4f}")

        st.subheader("Objective breakdown by sprint")
        obj_rows = []
        for i in inst.S:
            row = {
                "Sprint": i,
                "Discount": round(obj_details[i]["discount"], 4),
                "Story term": round(obj_details[i]["story_term"], 4),
                "Affinity term": round(obj_details[i]["affinity_term"], 4),
                "Penalty term": round(obj_details[i]["penalty_term"], 4),
                "Contribution": round(obj_details[i]["total_contribution"], 4),
            }
            obj_rows.append(row)
        st.dataframe(obj_rows, use_container_width=True)