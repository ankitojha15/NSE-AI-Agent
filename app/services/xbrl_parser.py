import xml.etree.ElementTree as ET


class XBRLParser:
    """
    Parse XBRL XML documents.

    Responsible only for reading XML.
    It does not download or store data.
    """

    def parse(self, xml_content: str):
        """
        Convert XML text into an ElementTree object.

        Parameters
        ----------
        xml_content : str
            Raw XML downloaded from NSE.

        Returns
        -------
        Element
            Root element of the XML tree.
        """

        return ET.fromstring(xml_content)

    def print_financial_tags(self, root):
        """
        Print financial tags that belong to the BSE/NSE taxonomy.
        """

        found = set()

        for element in root.iter():

            if "in-bse-fin" in element.tag:
                found.add(element.tag)

        for tag in sorted(found):
            print(tag)

    def export_tags(self, root, filename: str = "tags.txt"):
        """
        Export all unique XML tags to a text file.
        """

        tags = sorted({element.tag for element in root.iter()})

        with open(filename, "w") as file:
            for tag in tags:
                file.write(tag + "\n")

        print(f"Exported {len(tags)} tags.")