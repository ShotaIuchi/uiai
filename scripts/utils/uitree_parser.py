"""UITree XML parser for Android UI hierarchy."""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass


@dataclass
class UIElement:
    """Represents a UI element found in the UITree."""

    text: str
    resource_id: str
    class_name: str
    content_desc: str
    bounds: str
    center_x: int
    center_y: int
    index: str
    checkable: str
    clickable: str
    focusable: str
    parent_hierarchy: list[str]


def parse_bounds(bounds_str: str) -> tuple[int, int, int, int]:
    """Parse bounds string '[x1,y1][x2,y2]' into (x1, y1, x2, y2)."""
    match = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds_str)
    if not match:
        raise ValueError(f"Invalid bounds format: {bounds_str}")
    return (
        int(match.group(1)),
        int(match.group(2)),
        int(match.group(3)),
        int(match.group(4)),
    )


def get_center(bounds_str: str) -> tuple[int, int]:
    """Calculate center coordinates from bounds string."""
    x1, y1, x2, y2 = parse_bounds(bounds_str)
    return ((x1 + x2) // 2, (y1 + y2) // 2)


def _get_parent_classes(node: ET.Element, tree_root: ET.Element) -> list[str]:
    """Walk up the tree to collect parent class names (up to 3 levels)."""
    parent_map = {child: parent for parent in tree_root.iter() for child in parent}
    parents = []
    current = node
    for _ in range(3):
        parent = parent_map.get(current)
        if parent is None:
            break
        parents.append(parent.get("class", ""))
        current = parent
    return parents


def _node_to_element(
    node: ET.Element, tree_root: ET.Element
) -> UIElement | None:
    """Convert an XML node to a UIElement."""
    bounds = node.get("bounds", "")
    if not bounds:
        return None
    try:
        cx, cy = get_center(bounds)
    except ValueError:
        return None

    return UIElement(
        text=node.get("text", ""),
        resource_id=node.get("resource-id", ""),
        class_name=node.get("class", ""),
        content_desc=node.get("content-desc", ""),
        bounds=bounds,
        center_x=cx,
        center_y=cy,
        index=node.get("index", ""),
        checkable=node.get("checkable", "false"),
        clickable=node.get("clickable", "false"),
        focusable=node.get("focusable", "false"),
        parent_hierarchy=_get_parent_classes(node, tree_root),
    )


def parse_uitree(xml_content: str) -> ET.Element:
    """Parse UITree XML content and return root element."""
    return ET.fromstring(xml_content)


def find_by_text(
    root: ET.Element, search_text: str, match_type: str = "exact"
) -> UIElement | None:
    """Find element by text attribute.

    Args:
        root: UITree root element.
        search_text: Text to search for.
        match_type: 'exact' for exact match, 'contains' for substring.

    Returns:
        UIElement if found, None otherwise.
    """
    for node in root.iter("node"):
        text = node.get("text", "")
        if match_type == "exact" and text == search_text:
            return _node_to_element(node, root)
        if match_type == "contains" and search_text in text:
            return _node_to_element(node, root)
    return None


def find_by_resource_id(
    root: ET.Element, resource_id: str
) -> UIElement | None:
    """Find element by resource-id attribute."""
    for node in root.iter("node"):
        if node.get("resource-id", "") == resource_id:
            return _node_to_element(node, root)
    return None


def find_by_content_desc(
    root: ET.Element, desc: str, match_type: str = "contains"
) -> UIElement | None:
    """Find element by content-desc attribute."""
    for node in root.iter("node"):
        cd = node.get("content-desc", "")
        if match_type == "exact" and cd == desc:
            return _node_to_element(node, root)
        if match_type == "contains" and desc in cd:
            return _node_to_element(node, root)
    return None


def find_edit_text(
    root: ET.Element, hint: str = ""
) -> UIElement | None:
    """Find an EditText element, optionally near a hint/label text.

    Args:
        root: UITree root element.
        hint: Optional field hint (e.g. 'メールアドレス') to narrow search.

    Returns:
        UIElement of the EditText, or None.
    """
    edit_texts = []
    for node in root.iter("node"):
        cls = node.get("class", "")
        if "EditText" in cls:
            edit_texts.append(node)

    if not edit_texts:
        return None

    if not hint:
        return _node_to_element(edit_texts[0], root)

    # Try to find EditText with matching hint text
    for node in edit_texts:
        text = node.get("text", "")
        desc = node.get("content-desc", "")
        rid = node.get("resource-id", "")
        if hint in text or hint in desc or hint.lower() in rid.lower():
            return _node_to_element(node, root)

    # Proximity search: find label with hint text, then nearest EditText
    for label_node in root.iter("node"):
        if hint in label_node.get("text", ""):
            label_bounds = label_node.get("bounds", "")
            if not label_bounds:
                continue
            _, label_y1, _, label_y2 = parse_bounds(label_bounds)
            label_center_y = (label_y1 + label_y2) // 2

            best = None
            best_dist = float("inf")
            for et_node in edit_texts:
                et_bounds = et_node.get("bounds", "")
                if not et_bounds:
                    continue
                _, ey1, _, ey2 = parse_bounds(et_bounds)
                et_center_y = (ey1 + ey2) // 2
                dist = abs(et_center_y - label_center_y)
                if dist < best_dist:
                    best_dist = dist
                    best = et_node
            if best is not None:
                return _node_to_element(best, root)

    # Fallback: return first EditText
    return _node_to_element(edit_texts[0], root)


def text_exists(
    root: ET.Element, search_text: str, match_type: str = "exact"
) -> bool:
    """Check if text exists anywhere in the UITree.

    Args:
        root: UITree root element.
        search_text: Text to search for.
        match_type: 'exact' or 'contains'.

    Returns:
        True if text is found.
    """
    for node in root.iter("node"):
        text = node.get("text", "")
        if match_type == "exact" and text == search_text:
            return True
        if match_type == "contains" and search_text in text:
            return True
    return False


def resource_id_exists(root: ET.Element, resource_id: str) -> bool:
    """Check if a resource-id exists anywhere in the UITree.

    Args:
        root: UITree root element.
        resource_id: Resource ID to search for.

    Returns:
        True if the resource-id is found.
    """
    for node in root.iter("node"):
        if node.get("resource-id", "") == resource_id:
            return True
    return False


def class_exists(root: ET.Element, class_name: str) -> bool:
    """Check if a widget class exists anywhere in the UITree.

    Args:
        root: UITree root element.
        class_name: Fully qualified class name to search for.

    Returns:
        True if the class is found.
    """
    for node in root.iter("node"):
        if node.get("class", "") == class_name:
            return True
    return False


def count_elements(root: ET.Element, selector: dict) -> int:
    """Count elements matching a selector in the UITree.

    Args:
        root: UITree root element.
        selector: Dict with optional keys 'class', 'resource_id', 'text'.

    Returns:
        Number of matching elements.
    """
    count = 0
    target_class = selector.get("class", "")
    target_rid = selector.get("resource_id", "")
    target_text = selector.get("text", "")

    for node in root.iter("node"):
        if target_class and node.get("class", "") != target_class:
            continue
        if target_rid and node.get("resource-id", "") != target_rid:
            continue
        if target_text and target_text not in node.get("text", ""):
            continue
        count += 1
    return count


def extract_fingerprint(root: ET.Element) -> dict:
    """Extract a fingerprint from the UITree for verification.

    Extracts prominent texts, app-specific resource IDs, and structural
    widget classes to create a deterministic screen fingerprint.

    Args:
        root: UITree root element.

    Returns:
        Dict with 'texts', 'resource_ids', and 'classes' lists.
    """
    texts: list[str] = []
    resource_ids: list[str] = []
    classes: set[str] = set()

    structural_widgets = {
        "androidx.recyclerview.widget.RecyclerView",
        "androidx.viewpager2.widget.ViewPager2",
        "com.google.android.material.tabs.TabLayout",
        "com.google.android.material.bottomnavigation.BottomNavigationView",
        "com.google.android.material.navigation.NavigationView",
        "androidx.drawerlayout.widget.DrawerLayout",
        "com.google.android.material.appbar.AppBarLayout",
    }

    for node in root.iter("node"):
        # Collect prominent texts (2+ chars, non-dynamic)
        text = node.get("text", "")
        if len(text) >= 2 and not text.isdigit() and ":" not in text:
            texts.append(text)

        # Collect app-specific resource IDs (exclude android:id/)
        rid = node.get("resource-id", "")
        if rid and not rid.startswith("android:id/"):
            resource_ids.append(rid)

        # Collect structural widget classes
        cls = node.get("class", "")
        if cls in structural_widgets:
            classes.add(cls)

    return {
        "texts": texts,
        "resource_ids": resource_ids,
        "classes": sorted(classes),
    }


def resolve_element(
    root: ET.Element, compiled_step: dict
) -> UIElement | None:
    """Resolve an element using compiled metadata with fallback chain.

    Resolution priority:
    1. resource_id (most stable)
    2. text exact match
    3. content_desc
    4. class + parent hierarchy (last resort)

    Args:
        root: UITree root element.
        compiled_step: Compiled strategy dict with element_metadata.

    Returns:
        UIElement if found, None otherwise.
    """
    metadata = compiled_step.get("element_metadata")
    if not metadata:
        # No metadata, try search_text
        search_text = compiled_step.get("search_text", "")
        if search_text:
            match_type = compiled_step.get("match_type", "exact")
            return find_by_text(root, search_text, match_type)
        return None

    # 1. Try resource_id
    rid = metadata.get("resource_id", "")
    if rid:
        elem = find_by_resource_id(root, rid)
        if elem:
            return elem

    # 2. Try text
    search_text = compiled_step.get("search_text", "")
    if search_text:
        elem = find_by_text(root, search_text)
        if elem:
            return elem

    # 3. Try content_desc
    cd = metadata.get("content_desc", "")
    if cd:
        elem = find_by_content_desc(root, cd)
        if elem:
            return elem

    # 4. Try class match
    target_class = metadata.get("class", "")
    if target_class:
        for node in root.iter("node"):
            if node.get("class", "") == target_class:
                return _node_to_element(node, root)

    return None
