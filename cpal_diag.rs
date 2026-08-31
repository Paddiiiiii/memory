fn main() {
  println!(\"default host: {:?}\", cpal::default_host().id());
  for host in cpal::available_hosts() {
    println!(\"host: {:?}\", host);
    if let Ok(h) = cpal::host_from_id(host) {
      match h.input_devices() {
        Ok(devs) => {
          let mut n=0;
          for d in devs {
            n+=1;
            println!(\"  in: {:?}\", d.name());
          }
          if n==0 { println!(\"  (no input devices)\"); }
        }
        Err(e) => println!(\"  err: {e}\"),
      }
    }
  }
}
