require "base64"
require "json"
require "mathtype_to_mathml_plus"

PRIVATE_USE_RANGE = (0xE000..0xF8FF)
FIXED_ARITY_ELEMENTS = {
  "mfrac" => 2,
  "mroot" => 2,
  "msub" => 2,
  "msup" => 2,
  "munder" => 2,
  "mover" => 2,
  "msubsup" => 3,
  "munderover" => 3,
}.freeze

# Equation Editor permits a prescript-only object whose base is the following
# Word text run (for example, the "Zn" in a nuclide symbol). The upstream
# mover assumes that base is inside the OLE object and dereferences a missing
# sibling. Supply a zero-width structural base so the prescripts remain
# editable and the following Word text can stay outside the formula.
module MathTypeToMathMLPlus
  class Mover
    alias_method :question_bank_following_siblings, :new_following_siblings

    def new_following_siblings(element)
      siblings = question_bank_following_siblings(element)
      return siblings unless siblings.empty?

      siblings.push(Nokogiri::XML::Node.new("slot", mathtype))
      siblings
    end
  end
end

def ensure_equation_options(converter)
  document = converter.instance_variable_get(:@mathtype)
  mtef = document&.at_xpath("//mtef")
  return if mtef.nil? || mtef.at_xpath("./equation_options")

  # Microsoft Equation Editor 3.0 stores MTEF 3 data without the
  # equation_options node expected by mathtype_to_mathml_plus's stylesheet.
  # The Word paragraph tells the Python importer whether the formula is inline
  # or displayed, so "inline" is a safe structural default at this stage.
  options = Nokogiri::XML::Node.new("equation_options", document)
  options.content = "inline"
  mtef.prepend_child(options)
end

def mathtype_character_map(converter)
  @mathtype_character_map ||= begin
    path = File.join(
      File.dirname(converter.path_to_xslt),
      "xsl",
      "fontmaps",
      "MathType_MTCode.xml"
    )
    document = Nokogiri::XML(File.read(path))
    document.xpath("//symbol[@number][@char]").each_with_object({}) do |symbol, result|
      codepoint = symbol["number"].to_i(16)
      next unless PRIVATE_USE_RANGE.cover?(codepoint)
      character = symbol["char"]
      next if character.nil? || character.empty?

      result[codepoint.chr(Encoding::UTF_8)] = character
    end
  end
end

def normalize_mathml(mathml, converter)
  document = Nokogiri::XML(mathml)
  # Some MTEF 3 templates emit an extra, empty trailing slot. Fixed-arity
  # MathML elements reject it, even though it has no visual content.
  document.xpath("//*").each do |node|
    expected_children = FIXED_ARITY_ELEMENTS[node.name]
    next unless expected_children

    children = node.element_children
    while children.length > expected_children
      trailing = children.last
      break unless trailing.name == "mrow" &&
                   trailing.element_children.empty? &&
                   trailing.text.strip.empty?

      trailing.remove
      children = node.element_children
    end
  end
  replacements = mathtype_character_map(converter)
  document.xpath("//text()").each do |node|
    node.content = node.text.each_char.map { |char| replacements.fetch(char, char) }.join
  end
  unsupported = document.xpath("//text()").flat_map do |node|
    node.text.each_codepoint.select { |codepoint| PRIVATE_USE_RANGE.cover?(codepoint) }
  end.uniq
  unless unsupported.empty?
    codes = unsupported.map { |codepoint| format("U+%04X", codepoint) }.join(", ")
    raise NotImplementedError, "Unsupported Equation Editor character(s): #{codes}"
  end
  document.to_xml
end

entries = []
if ARGV == ["--stdin-json"]
  manifest = JSON.parse(STDIN.read)
  if manifest.is_a?(Hash)
    manifest.each do |marker, path|
      entries << [marker.to_s, path.to_s]
    end
  end
else
  ARGV.each do |argument|
    entries << argument.split("=", 2)
  end
end

entries.each do |marker, path|
  next if marker.nil? || marker.empty? || path.nil? || path.empty?

  begin
    converter = MathTypeToMathMLPlus::Converter.new(path)
    ensure_equation_options(converter)
    mathml = converter.convert.to_s
    mathml = normalize_mathml(mathml, converter)
    mathml = mathml.encode("UTF-8", invalid: :replace, undef: :replace, replace: "")
    puts JSON.generate(
      {
        id: marker,
        ok: true,
        mathml: Base64.strict_encode64(mathml),
      }
    )
  rescue StandardError, NotImplementedError => error
    puts JSON.generate(
      {
        id: marker,
        ok: false,
        error: "#{error.class}: #{error.message}",
      }
    )
  end
end
