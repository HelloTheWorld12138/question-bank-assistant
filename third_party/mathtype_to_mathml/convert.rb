require "base64"
require "json"
require "mathtype_to_mathml_plus"

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
    mathml = MathTypeToMathMLPlus::Converter.new(path).convert.to_s
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
